"""Write score.py predictions for a local directory or a Hugging Face model name.

CPU only. The prompt matches training/train.py.
"""
import argparse
import json
import os


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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--max-new-tokens", type=int, default=64)
    args = parser.parse_args()

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    torch.set_num_threads(int(os.environ.get("PREDICT_THREADS", "4")))
    tokenizer = AutoTokenizer.from_pretrained(args.model)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(args.model)
    model.to("cpu")
    model.eval()

    rows = [json.loads(line) for line in open(args.input, encoding="utf-8") if line.strip()]
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        for row in rows:
            prompt = f"Command: {row['text']}\nJSON:"
            encoded = tokenizer(prompt, return_tensors="pt")
            with torch.no_grad():
                generated = model.generate(
                    **encoded,
                    max_new_tokens=args.max_new_tokens,
                    do_sample=False,
                    pad_token_id=tokenizer.pad_token_id,
                )
            new_tokens = generated[0][encoded["input_ids"].shape[1]:]
            text = tokenizer.decode(new_tokens, skip_special_tokens=True)
            handle.write(json.dumps({"id": row["id"], "prediction": extract_json(text)}) + "\n")
            handle.flush()
    print(f"wrote {args.out} ({len(rows)} predictions)")


if __name__ == "__main__":
    main()
