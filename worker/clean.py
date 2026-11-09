"""Clean teacher shards into datasets/v1/train.jsonl (Task 1).

Rejection precedence. A record is counted under exactly one reason, in this order:
  (a) teacher_raw is not a JSON object
  (b) the object's keys are not exactly intent, date, time, place
  (c) intent is not one of the eight allowed values
  (d) a slot is neither null nor a string that appears in the command
  (e) duplicate command text; the record with the smallest id is kept

input = (a) + (b) + (c) + (d) + duplicates + kept

The written records stay in id order and keep the original id, the original command
text, and the exact teacher response.
"""
import argparse
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import storage  # noqa: E402

KEYS = ("intent", "date", "time", "place")
KEY_SET = set(KEYS)
INTENTS = {
    "alarm_set",
    "alarm_query",
    "calendar_set",
    "calendar_query",
    "calendar_remove",
    "weather_query",
    "datetime_query",
    "recommendation_events",
}
SHARD_NAME = re.compile(r"shard-\d+\.jsonl$")


def norm(value):
    return " ".join(str(value).strip().lower().split())


def classify(record):
    """Return ('keep', object) or a single letter reason a/b/c/d."""
    raw = record.get("teacher_raw")
    if isinstance(raw, dict):
        obj = raw
    else:
        try:
            obj = json.loads(str(raw).strip())
        except (json.JSONDecodeError, TypeError, ValueError):
            return "a"
    if not isinstance(obj, dict):
        return "a"
    if set(obj.keys()) != KEY_SET:
        return "b"
    if obj.get("intent") not in INTENTS:
        return "c"
    text = norm(record.get("text", ""))
    for key in ("date", "time", "place"):
        value = obj[key]
        if value is None:
            continue
        if not isinstance(value, str) or norm(value) not in text:
            return "d"
    return ("keep", obj)


def clean_records(records):
    counts = {"input": 0, "a": 0, "b": 0, "c": 0, "d": 0, "duplicates": 0, "kept": 0}
    survivors = []
    for record in records:
        counts["input"] += 1
        result = classify(record)
        if isinstance(result, tuple) and result[0] == "keep":
            survivors.append((record["id"], record["text"], record.get("teacher_raw"), result[1]))
        else:
            counts[result] += 1

    best = {}
    for sid, text, raw, obj in survivors:
        if text not in best or sid < best[text][0]:
            best[text] = (sid, text, raw, obj)
    counts["duplicates"] = len(survivors) - len(best)
    kept = sorted(best.values(), key=lambda item: item[0])
    counts["kept"] = len(kept)
    rows = []
    for sid, text, raw, obj in kept:
        if not isinstance(raw, str):
            raw = json.dumps(raw, ensure_ascii=False)
        rows.append({
            "id": sid,
            "text": text,
            "teacher_raw": raw,
            "intent": obj["intent"],
            "date": obj["date"],
            "time": obj["time"],
            "place": obj["place"],
        })
    return rows, counts


def shard_keys(bucket, prefix):
    keys = []
    for key in storage.list_keys(bucket, prefix):
        if SHARD_NAME.search(key):
            keys.append(key)
    return keys


def read_shards(bucket, prefix):
    records = []
    used = []
    for key in shard_keys(bucket, prefix):
        used.append(key)
        text = storage.read_text(bucket, key)
        for line in text.splitlines():
            if line.strip():
                records.append(json.loads(line))
    return records, used


def render_jsonl(rows):
    return "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def print_counts(counts):
    total = counts["a"] + counts["b"] + counts["c"] + counts["d"] + counts["duplicates"] + counts["kept"]
    print("Cleaning counts")
    print(f"  input records           {counts['input']}")
    print(f"  (a) invalid JSON        {counts['a']}")
    print(f"  (b) incorrect keys      {counts['b']}")
    print(f"  (c) invalid intent      {counts['c']}")
    print(f"  (d) invalid slot        {counts['d']}")
    print(f"  duplicates              {counts['duplicates']}")
    print(f"  kept                    {counts['kept']}")
    print(f"  a+b+c+d+duplicates+kept {total} (matches input: {total == counts['input']})")
    return total == counts["input"]


def audit_coverage(pool_path, records):
    with open(pool_path, encoding="utf-8") as handle:
        pool_ids = [json.loads(line)["id"] for line in handle if line.strip()]
    seen = [rec["id"] for rec in records]
    missing = sorted(set(pool_ids) - set(seen))
    extra = sorted(set(seen) - set(pool_ids))
    dup = sorted({sid for sid in seen if seen.count(sid) > 1})
    print(f"Coverage: pool={len(pool_ids)} shard_records={len(seen)} missing={len(missing)} extra={len(extra)} repeated={len(dup)}")
    return {"missing": missing, "extra": extra, "repeated_ids": dup, "pool": len(pool_ids), "shard_records": len(seen)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket", default=os.environ.get("DATASETS_BUCKET", "datasets"))
    parser.add_argument("--prefix", default="teacher/shard-")
    parser.add_argument("--out-prefix", default="v1")
    parser.add_argument("--counts-out", default="results/clean_counts.json")
    parser.add_argument("--pool", default="data/commands_pool.jsonl")
    args = parser.parse_args()

    records, used = read_shards(args.bucket, args.prefix)
    if not records:
        sys.exit(f"no shard records under {args.bucket}/{args.prefix}")
    print("shards:", ", ".join(used))
    coverage = audit_coverage(args.pool, records) if os.path.exists(args.pool) else None
    rows, counts = clean_records(records)
    if not print_counts(counts):
        sys.exit("count identity failed")

    body = render_jsonl(rows)
    digest = sha256_text(body)
    storage.ensure_bucket(args.bucket)
    storage.write_text(args.bucket, f"{args.out_prefix}/train.jsonl", body)
    storage.write_text(args.bucket, f"{args.out_prefix}/train.sha256", f"{digest}  train.jsonl\n")
    print(f"wrote {args.bucket}/{args.out_prefix}/train.jsonl")
    print(f"sha256 {digest}")

    if args.counts_out:
        os.makedirs(os.path.dirname(args.counts_out) or ".", exist_ok=True)
        report = {"counts": counts, "sha256": digest, "shards": used, "coverage": coverage,
                  "precedence": ["a invalid json", "b incorrect keys", "c invalid intent", "d invalid slot", "e duplicate text, keep smallest id"]}
        with open(args.counts_out, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)
            handle.write("\n")
        # Evidence copy of the checksum, because datasets/ is not committed.
        with open(os.path.join("results", "train.sha256"), "w", encoding="utf-8") as handle:
            handle.write(f"{digest}  train.jsonl\n")


if __name__ == "__main__":
    main()
