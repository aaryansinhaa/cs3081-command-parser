"""Label data/validation.jsonl with the same teacher settings used in Task 1.

Writes results/pred_teacher.jsonl for tools/score.py. The teacher reply is stored unchanged.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "worker"))
import worker  # noqa: E402


def main():
    os.environ.setdefault("TEACHER_MODEL", "phi3.5")
    prompt = worker.load_prompt()
    rows = [json.loads(line) for line in open("data/validation.jsonl", encoding="utf-8") if line.strip()]
    os.makedirs("results", exist_ok=True)
    out_path = "results/pred_teacher.jsonl"
    with open(out_path, "w", encoding="utf-8") as handle:
        for index, row in enumerate(rows, 1):
            raw = None
            last = None
            for attempt in range(1, 4):
                try:
                    raw = worker.call_teacher(prompt, row["text"])
                    break
                except Exception as exc:
                    last = exc
                    print(f"retry {row['id']} {exc}", flush=True)
            if raw is None:
                sys.exit(f"teacher failed on {row['id']}: {last}")
            handle.write(json.dumps({"id": row["id"], "prediction": raw}, ensure_ascii=False) + "\n")
            handle.flush()
            if index % 10 == 0:
                print(f"teacher {index}/{len(rows)}", flush=True)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
