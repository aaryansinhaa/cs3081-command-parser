"""Parallel teacher-labelling worker.

A command belongs to this worker when its line number (from zero) satisfies
line_number % SHARD_COUNT == SHARD_INDEX. Each assigned command is sent to Ollama
(phi3.5, temperature 0, seed 42). The raw reply is stored unchanged.

Output object: datasets/teacher/shard-<index>.jsonl
    {"id": "C0001", "text": "...", "teacher_raw": "<exact teacher reply>"}

Permanent failures are NOT written as empty successes. They are appended to
datasets/teacher/shard-<index>.failures.jsonl and the process exits non-zero so the
gap is visible. Re-running the worker resumes from ids already present in the shard.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

import storage

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
TEACHER_MODEL = os.environ.get("TEACHER_MODEL", "phi3.5")
PROMPT_FILE = os.environ.get("PROMPT_FILE", "prompts/teacher_prompt.txt")
DATASETS_BUCKET = os.environ.get("DATASETS_BUCKET", "datasets")
SEED = int(os.environ.get("TEACHER_SEED", "42"))
TEMPERATURE = float(os.environ.get("TEACHER_TEMPERATURE", "0"))
MAX_TOKENS = int(os.environ.get("TEACHER_MAX_TOKENS", "96"))
NUM_CTX = int(os.environ.get("TEACHER_NUM_CTX", "2048"))
RETRIES = int(os.environ.get("TEACHER_RETRIES", "4"))
POOL_KEY = os.environ.get("POOL_KEY", "commands_pool.jsonl")


def shard_index():
    for var in ("SHARD_INDEX", "JOB_COMPLETION_INDEX"):
        raw = os.environ.get(var)
        if raw not in (None, ""):
            return int(raw)
    sys.exit("SHARD_INDEX (or JOB_COMPLETION_INDEX) must be set")


def assigned(line_number, shard_count, index):
    return line_number % shard_count == index


def load_prompt():
    with open(PROMPT_FILE, encoding="utf-8") as handle:
        return handle.read()


def call_teacher(prompt_template, command):
    prompt = prompt_template.replace("{{COMMAND}}", command)
    payload = json.dumps({
        "model": TEACHER_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": TEMPERATURE,
            "seed": SEED,
            "num_predict": MAX_TOKENS,
            "num_ctx": NUM_CTX,
        },
    }).encode("utf-8")
    request = urllib.request.Request(
        f"{OLLAMA_HOST}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        body = json.loads(response.read().decode("utf-8"))
    if body.get("error"):
        raise RuntimeError(body["error"])
    raw = body.get("response")
    if not isinstance(raw, str) or not raw.strip():
        raise RuntimeError("empty teacher response")
    return raw


def read_pool():
    try:
        text = storage.read_text(DATASETS_BUCKET, POOL_KEY)
    except Exception:
        local = os.path.join("data", "commands_pool.jsonl")
        with open(local, encoding="utf-8") as handle:
            text = handle.read()
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _ids_in_text(text):
    done = set()
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            done.add(json.loads(line)["id"])
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
    return done


def load_existing(local_path, key):
    """Return completed ids and the existing JSONL text, preferring a non-empty local file."""
    text = ""
    if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
        with open(local_path, encoding="utf-8") as handle:
            text = handle.read()
    elif storage.use_s3() and storage.exists(DATASETS_BUCKET, key):
        text = storage.read_text(DATASETS_BUCKET, key)
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, "w", encoding="utf-8") as handle:
            handle.write(text)
    return _ids_in_text(text)


def main():
    index = shard_index()
    count = int(os.environ.get("SHARD_COUNT", "2"))
    if count < 1 or not 0 <= index < count:
        sys.exit(f"invalid shard index {index} for count {count}")

    prompt = load_prompt()
    commands = read_pool()
    mine = [(n, row) for n, row in enumerate(commands) if assigned(n, count, index)]

    storage.ensure_bucket(DATASETS_BUCKET)
    data_root = os.environ.get("WORKER_DATA_DIR", "datasets")
    local_path = os.path.join(data_root, "teacher", f"shard-{index}.jsonl")
    fail_path = os.path.join(data_root, "teacher", f"shard-{index}.failures.jsonl")
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    key = f"teacher/shard-{index}.jsonl"
    fail_key = f"teacher/shard-{index}.failures.jsonl"
    done = load_existing(local_path, key)

    print(
        f"[shard {index}/{count}] assigned={len(mine)} already_done={len(done)} "
        f"model={TEACHER_MODEL} temperature={TEMPERATURE} seed={SEED}",
        flush=True,
    )

    failures = []
    completed = 0
    with open(local_path, "a", encoding="utf-8") as out:
        for n, (line_no, cmd) in enumerate(mine, 1):
            if cmd["id"] in done:
                completed += 1
                continue
            raw = None
            last_error = None
            for attempt in range(1, RETRIES + 1):
                try:
                    raw = call_teacher(prompt, cmd["text"])
                    break
                except (urllib.error.URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as exc:
                    last_error = f"{type(exc).__name__}: {exc}"
                    print(
                        f"[shard {index}] retry {attempt}/{RETRIES} {cmd['id']} ({last_error})",
                        flush=True,
                    )
                    time.sleep(min(2 * attempt, 10))
            if raw is None:
                failure = {
                    "id": cmd["id"],
                    "text": cmd["text"],
                    "line_number": line_no,
                    "error": last_error or "unknown",
                }
                failures.append(failure)
                print(f"[shard {index}] FAILED {cmd['id']}: {failure['error']}", flush=True)
                continue
            out.write(json.dumps(
                {"id": cmd["id"], "text": cmd["text"], "teacher_raw": raw},
                ensure_ascii=False,
            ) + "\n")
            out.flush()
            done.add(cmd["id"])
            completed += 1
            if completed % 10 == 0 or n == len(mine):
                print(f"[shard {index}] {completed}/{len(mine)}", flush=True)
                try:
                    storage.upload_file(DATASETS_BUCKET, key, local_path)
                except Exception as exc:
                    print(f"[shard {index}] upload warning: {exc}", flush=True)

    storage.upload_file(DATASETS_BUCKET, key, local_path)
    if failures:
        fail_text = "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in failures)
        with open(fail_path, "a", encoding="utf-8") as handle:
            handle.write(fail_text)
        if storage.use_s3():
            storage.upload_file(DATASETS_BUCKET, fail_key, fail_path)
        print(f"[shard {index}] {len(failures)} permanent failures -> {fail_key}", flush=True)
        sys.exit(1)
    print(f"[shard {index}] done -> {DATASETS_BUCKET}/{key}", flush=True)


if __name__ == "__main__":
    main()
