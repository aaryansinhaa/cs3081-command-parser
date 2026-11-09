"""Upload models/v1 and models/v2 to the models bucket when those directories exist."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "worker"))
import storage  # noqa: E402


def upload_tree(version):
    local = os.path.join("models", version)
    if not os.path.isdir(local):
        print(f"skip {version}: {local} missing")
        return
    storage.ensure_bucket("models")
    names = sorted(os.listdir(local))
    # Small config/tokenizer files first; weights last so a retry can resume.
    names.sort(key=lambda n: (n == "model.safetensors", n))
    for name in names:
        path = os.path.join(local, name)
        if not os.path.isfile(path):
            continue
        key = f"{version}/{name}"
        for attempt in range(1, 6):
            try:
                storage.upload_file("models", key, path)
                print(f"uploaded models/{key}", flush=True)
                break
            except Exception as exc:
                if attempt == 5:
                    raise
                print(f"retry {attempt}/5 models/{key}: {exc}", flush=True)
    archive = os.path.join("models", f"{version}.tar.gz")
    if os.path.isfile(archive):
        storage.upload_file("models", f"{version}.tar.gz", archive)
        print(f"uploaded models/{version}.tar.gz", flush=True)


def main():
    upload_tree("v1")
    upload_tree("v2")


if __name__ == "__main__":
    main()
