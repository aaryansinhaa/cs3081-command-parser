"""Object storage helper for SeaweedFS (S3) or the local filesystem.

If S3_ENDPOINT is set, objects are read and written with boto3. Otherwise files are stored
under LOCAL_ROOT (default: the current directory). A key is always <bucket>/<path>, for
example datasets/teacher/shard-0.jsonl.

Credentials come from AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY. They are never logged.
"""
import glob
import os

LOCAL_ROOT = os.environ.get("LOCAL_ROOT", ".")


def use_s3():
    return bool(os.environ.get("S3_ENDPOINT"))


def _client():
    import boto3
    from botocore.client import Config

    return boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT"],
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", ""),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", ""),
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            retries={"max_attempts": 8, "mode": "adaptive"},
            connect_timeout=20,
            read_timeout=120,
        ),
    )


def ensure_bucket(bucket):
    if not use_s3():
        os.makedirs(os.path.join(LOCAL_ROOT, bucket), exist_ok=True)
        return
    client = _client()
    names = {b["Name"] for b in client.list_buckets().get("Buckets", [])}
    if bucket not in names:
        client.create_bucket(Bucket=bucket)


def write_text(bucket, path, text):
    if use_s3():
        _client().put_object(Bucket=bucket, Key=path, Body=text.encode("utf-8"))
        return
    dest = os.path.join(LOCAL_ROOT, bucket, path)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w", encoding="utf-8") as handle:
        handle.write(text)


def write_bytes(bucket, path, data):
    if use_s3():
        _client().put_object(Bucket=bucket, Key=path, Body=data)
        return
    dest = os.path.join(LOCAL_ROOT, bucket, path)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as handle:
        handle.write(data)


def read_text(bucket, path):
    if use_s3():
        obj = _client().get_object(Bucket=bucket, Key=path)
        return obj["Body"].read().decode("utf-8")
    with open(os.path.join(LOCAL_ROOT, bucket, path), encoding="utf-8") as handle:
        return handle.read()


def exists(bucket, path):
    if use_s3():
        try:
            _client().head_object(Bucket=bucket, Key=path)
            return True
        except Exception:
            return False
    return os.path.isfile(os.path.join(LOCAL_ROOT, bucket, path))


def _object_size(bucket, path):
    try:
        return _client().head_object(Bucket=bucket, Key=path)["ContentLength"]
    except Exception:
        return None


def upload_file(bucket, path, local_file, skip_if_unchanged=True):
    if use_s3():
        size = os.path.getsize(local_file)
        if skip_if_unchanged:
            remote = _object_size(bucket, path)
            if remote is not None and remote == size:
                return
        client = _client()
        # One PUT avoids fragile multipart uploads through kubectl port-forward.
        if size <= 400 * 1024 * 1024:
            with open(local_file, "rb") as handle:
                client.put_object(Bucket=bucket, Key=path, Body=handle)
            return
        from boto3.s3.transfer import TransferConfig

        client.upload_file(
            local_file,
            bucket,
            path,
            Config=TransferConfig(
                multipart_threshold=512 * 1024 * 1024,
                max_concurrency=1,
                use_threads=False,
            ),
        )
        return
    dest = os.path.join(LOCAL_ROOT, bucket, path)
    if os.path.abspath(dest) == os.path.abspath(local_file):
        return
    with open(local_file, "rb") as handle:
        write_bytes(bucket, path, handle.read())


def download_file(bucket, path, local_file):
    os.makedirs(os.path.dirname(local_file) or ".", exist_ok=True)
    if use_s3():
        _client().download_file(bucket, path, local_file)
        return
    src = os.path.join(LOCAL_ROOT, bucket, path)
    if os.path.abspath(src) == os.path.abspath(local_file):
        return
    with open(src, "rb") as src_handle, open(local_file, "wb") as dst_handle:
        dst_handle.write(src_handle.read())


def list_keys(bucket, prefix):
    if use_s3():
        client = _client()
        keys, token = [], None
        while True:
            kwargs = {"Bucket": bucket, "Prefix": prefix}
            if token:
                kwargs["ContinuationToken"] = token
            resp = client.list_objects_v2(**kwargs)
            keys.extend(obj["Key"] for obj in resp.get("Contents", []))
            if not resp.get("IsTruncated"):
                break
            token = resp.get("NextContinuationToken")
        return sorted(keys)
    base = os.path.join(LOCAL_ROOT, bucket)
    hits = glob.glob(os.path.join(base, prefix + "*"))
    return sorted(os.path.relpath(hit, base).replace(os.sep, "/") for hit in hits)
