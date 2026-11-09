"""Create the datasets and models buckets and upload commands_pool.jsonl."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "worker"))
import storage  # noqa: E402


def main():
    for bucket in ("datasets", "models"):
        storage.ensure_bucket(bucket)
        print(f"bucket ready: {bucket}")
    with open(os.path.join("data", "commands_pool.jsonl"), encoding="utf-8") as handle:
        storage.write_text("datasets", "commands_pool.jsonl", handle.read())
    print("uploaded datasets/commands_pool.jsonl")


if __name__ == "__main__":
    main()
