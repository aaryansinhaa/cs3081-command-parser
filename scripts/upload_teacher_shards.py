"""Upload local datasets/teacher/shard-*.jsonl to the datasets bucket."""
import glob
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "worker"))
import storage  # noqa: E402


def main():
    storage.ensure_bucket("datasets")
    for path in sorted(glob.glob("datasets/teacher/shard-*.jsonl")):
        name = os.path.basename(path)
        key = f"teacher/{name}"
        storage.upload_file("datasets", key, path, skip_if_unchanged=False)
        print(f"uploaded datasets/{key}")


if __name__ == "__main__":
    main()
