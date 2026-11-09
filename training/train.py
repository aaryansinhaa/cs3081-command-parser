"""Sequence-level distillation of EleutherAI/pythia-70m on CPU.

Each example is:

    Command: <command>
    JSON: <teacher JSON>

Hyperparameters come only from training/config.yaml. Loss is computed on the target
tokens. Prompt tokens and padding tokens are masked with -100.

  make train
  make train SUBSET=50
"""
import argparse
import csv
import hashlib
import json
import os
import random
import sys
import tarfile

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "worker"))
import storage  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
KEYS = ("intent", "date", "time", "place")


def load_config():
    with open(os.path.join(HERE, "config.yaml"), encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_rows(cfg, limit):
    try:
        text = storage.read_text(cfg["datasets_bucket"], cfg["train_file"])
    except Exception:
        with open(os.path.join(ROOT, "datasets", "v1", "train.jsonl"), encoding="utf-8") as handle:
            text = handle.read()
    rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    return rows[:limit]


def teacher_target(row):
    obj = {key: row[key] for key in KEYS}
    return json.dumps(obj, ensure_ascii=False)


def build_example(tokenizer, row, max_len):
    """Mask the command prompt. The prompt must be a token prefix of the full sequence.

    A trailing space after "JSON:" would be its own token when the prompt is encoded
    alone, but would merge into the following token inside the full string. Ending the
    prompt at "JSON:" and putting the space on the target keeps the mask boundary exact.
    """
    target = teacher_target(row)
    prompt = f"Command: {row['text']}\nJSON:"
    full = prompt + " " + target + tokenizer.eos_token
    ids = tokenizer(full, truncation=True, max_length=max_len, add_special_tokens=True)["input_ids"]
    prompt_ids = tokenizer(prompt, truncation=True, max_length=max_len, add_special_tokens=True)["input_ids"]
    prompt_len = len(prompt_ids)
    if ids[:prompt_len] != prompt_ids:
        # Fall back to the longest matching prefix so the label mask never covers a target token
        # and never leaves a prompt token unmasked when the tokenisation agrees.
        prompt_len = 0
        for i, tok in enumerate(prompt_ids):
            if i >= len(ids) or ids[i] != tok:
                break
            prompt_len = i + 1
    labels = [-100] * prompt_len + ids[prompt_len:]
    return ids, labels


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="v1", choices=("v1", "v2"))
    parser.add_argument("--subset", type=int, default=0)
    parser.add_argument("--no-upload", action="store_true")
    args = parser.parse_args()

    import torch
    from torch.utils.data import DataLoader, Dataset
    from transformers import AutoModelForCausalLM, AutoTokenizer

    cfg = load_config()
    if args.version == "v2":
        seed = int(cfg["seed_v2"])
        epochs = int(cfg["epochs_v2"])
    else:
        seed = int(cfg["seed"])
        epochs = int(cfg["epochs"])
    limit = args.subset if args.subset else int(cfg["train_limit"])
    torch.set_num_threads(int(cfg.get("num_threads", 4)))
    random.seed(seed)
    torch.manual_seed(seed)

    print(
        f"[train] version={args.version} seed={seed} lr={cfg['learning_rate']} "
        f"batch={cfg['batch_size']} epochs={epochs} max_seq_len={cfg['max_seq_len']} "
        f"limit={limit} device=cpu torch={torch.__version__}",
        flush=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(cfg["model_name"])
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(cfg["model_name"])
    model.to("cpu")
    model.train()

    rows = load_rows(cfg, limit)
    if len(rows) < limit and not args.subset:
        print(f"[train] warning: only {len(rows)} rows available (limit {limit})", flush=True)
    print(f"[train] examples={len(rows)}", flush=True)
    examples = [build_example(tokenizer, row, int(cfg["max_seq_len"])) for row in rows]

    class Rows(Dataset):
        def __len__(self):
            return len(examples)

        def __getitem__(self, index):
            return examples[index]

    pad_id = tokenizer.pad_token_id

    def collate(batch):
        width = max(len(ids) for ids, _ in batch)
        input_ids, attention, labels = [], [], []
        for ids, labs in batch:
            pad = width - len(ids)
            input_ids.append(ids + [pad_id] * pad)
            attention.append([1] * len(ids) + [0] * pad)
            labels.append(labs + [-100] * pad)
        return torch.tensor(input_ids), torch.tensor(attention), torch.tensor(labels)

    generator = torch.Generator()
    generator.manual_seed(seed)
    loader = DataLoader(
        Rows(),
        batch_size=int(cfg["batch_size"]),
        shuffle=True,
        collate_fn=collate,
        generator=generator,
    )
    optim = torch.optim.AdamW(model.parameters(), lr=float(cfg["learning_rate"]))

    loss_rows = []
    for epoch in range(1, epochs + 1):
        total, steps = 0.0, 0
        for input_ids, attention, labels in loader:
            optim.zero_grad()
            out = model(input_ids=input_ids, attention_mask=attention, labels=labels)
            out.loss.backward()
            optim.step()
            total += float(out.loss.item())
            steps += 1
        avg = total / max(steps, 1)
        loss_rows.append((epoch, round(avg, 6)))
        print(f"[train] epoch {epoch}/{epochs} loss {avg:.6f}", flush=True)

    loss_path = os.path.join(HERE, "loss.csv")
    with open(loss_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["epoch", "loss"])
        writer.writerows(loss_rows)
    version_loss = os.path.join(ROOT, "results", f"loss_{args.version}.csv")
    os.makedirs(os.path.dirname(version_loss), exist_ok=True)
    with open(version_loss, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["epoch", "loss"])
        writer.writerows(loss_rows)

    out_dir = os.path.join(ROOT, "models", args.version)
    os.makedirs(out_dir, exist_ok=True)
    model.save_pretrained(out_dir)
    tokenizer.save_pretrained(out_dir)

    archive = os.path.join(ROOT, "models", f"{args.version}.tar.gz")
    with tarfile.open(archive, "w:gz") as tar:
        for name in sorted(os.listdir(out_dir)):
            if name == "model.sha256":
                continue
            tar.add(os.path.join(out_dir, name), arcname=name)
    digest = hashlib.sha256(open(archive, "rb").read()).hexdigest()
    checksum_line = f"{digest}  {args.version}.tar.gz\n"
    with open(os.path.join(out_dir, "model.sha256"), "w", encoding="utf-8") as handle:
        handle.write(checksum_line)
    with open(os.path.join(ROOT, "results", f"model_{args.version}.sha256"), "w", encoding="utf-8") as handle:
        handle.write(checksum_line)
    print(f"[train] saved {out_dir} sha256 {digest}", flush=True)

    if not args.no_upload:
        try:
            storage.ensure_bucket(cfg["models_bucket"])
            for name in sorted(os.listdir(out_dir)):
                storage.upload_file(cfg["models_bucket"], f"{args.version}/{name}", os.path.join(out_dir, name))
            storage.upload_file(cfg["models_bucket"], f"{args.version}.tar.gz", archive)
            print(f"[train] uploaded to {cfg['models_bucket']}/{args.version}/", flush=True)
        except Exception as exc:
            print(f"[train] upload skipped ({exc})", flush=True)


if __name__ == "__main__":
    main()
