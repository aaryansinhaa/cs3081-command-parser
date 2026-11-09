"""Download the student model from object storage and validate its outputs."""
import json
import os
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_default_schema = os.path.join(_HERE, "schema.json")
if not os.path.exists(_default_schema):
    _default_schema = os.path.join(_HERE, "..", "data", "schema.json")
SCHEMA_PATH = os.environ.get("SCHEMA_PATH", _default_schema)
with open(SCHEMA_PATH, encoding="utf-8") as _handle:
    _SCHEMA = json.load(_handle)
KEYS = set(_SCHEMA["keys"])
INTENTS = set(_SCHEMA["intents"])


def extract_json(generated):
    text = generated.strip()
    start = text.find("{")
    if start == -1:
        return text
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    return text[start:]


def validate(raw):
    """Return the object when it matches schema.json, otherwise None."""
    try:
        obj = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(obj, dict) or set(obj.keys()) != KEYS:
        return None
    if not isinstance(obj.get("intent"), str) or obj["intent"] not in INTENTS:
        return None
    for key in ("date", "time", "place"):
        if obj[key] is not None and not isinstance(obj[key], str):
            return None
    return {key: obj[key] for key in ("intent", "date", "time", "place")}


def _download(model_uri):
    bucket, _, prefix = model_uri[len("s3://"):].partition("/")
    prefix = prefix.rstrip("/") + "/"
    import boto3
    from botocore.client import Config

    client = boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT"],
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", ""),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", ""),
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )
    dest = tempfile.mkdtemp(prefix="model-")
    token = None
    found = False
    while True:
        kwargs = {"Bucket": bucket, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        resp = client.list_objects_v2(**kwargs)
        for obj in resp.get("Contents", []):
            name = obj["Key"][len(prefix):]
            if not name or name.endswith("/"):
                continue
            target = os.path.join(dest, name)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            print(f"downloading s3://{bucket}/{obj['Key']}", flush=True)
            client.download_file(bucket, obj["Key"], target)
            found = True
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")
    if not found:
        raise RuntimeError(f"no objects under {model_uri}")
    checksum = os.path.join(dest, "model.sha256")
    if os.path.exists(checksum):
        print(f"checksum file present: {open(checksum, encoding='utf-8').read().strip()}", flush=True)
    return dest


def resolve_model_dir(model_uri):
    if model_uri.startswith("s3://"):
        return _download(model_uri)
    if model_uri.startswith("file://"):
        model_uri = model_uri[len("file://"):]
    if not os.path.isdir(model_uri):
        raise RuntimeError(f"MODEL_URI not found: {model_uri}")
    return model_uri


class Runner:
    def __init__(self):
        self.ready = False
        self.model = None
        self.tokenizer = None
        self.max_new_tokens = int(os.environ.get("MAX_NEW_TOKENS", "64"))

    def load(self):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        torch.set_num_threads(int(os.environ.get("TORCH_NUM_THREADS", "1")))
        local_dir = resolve_model_dir(os.environ["MODEL_URI"])
        self.tokenizer = AutoTokenizer.from_pretrained(local_dir)
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        self.model = AutoModelForCausalLM.from_pretrained(local_dir)
        self.model.to("cpu")
        self.model.eval()
        self.ready = True

    def raw_output(self, text):
        import torch

        prompt = f"Command: {text}\nJSON:"
        encoded = self.tokenizer(prompt, return_tensors="pt")
        with torch.no_grad():
            generated = self.model.generate(
                **encoded,
                max_new_tokens=self.max_new_tokens,
                do_sample=False,
                pad_token_id=self.tokenizer.pad_token_id,
            )
        new_tokens = generated[0][encoded["input_ids"].shape[1]:]
        decoded = self.tokenizer.decode(new_tokens, skip_special_tokens=True)
        return extract_json(decoded)
