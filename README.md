# Knowledge Distillation and Deployment of a Lightweight Command-Parsing Language Model on a Local Cloud

**Student:** Aaryan Kumar Sinha  
**Roll number:** 230101098  
**Course:** Cloud Computing (CS3081)

**GitHub repository:** https://github.com/aaryansinhaa/cs3081-command-parser

The repository URL above is the project remote. Model weights are published as a GitHub Release under the tag `model-v1`, not committed to Git. The release is created after training finishes; until that release exists, `make train` is how a fresh clone produces `models/v1`.

The service reads one English command and returns exactly four JSON keys:

```json
{"intent": "alarm_set", "date": "tomorrow", "time": "seven am", "place": null}
```

## Architecture

1. Two workers shard `data/commands_pool.jsonl` with `line_number % SHARD_COUNT == SHARD_INDEX` and ask local Ollama (`phi3.5`, temperature 0, seed 42) for a label. The raw reply is stored unchanged.
2. `worker/clean.py` rejects invalid replies with a fixed precedence and writes `datasets/v1/train.jsonl` plus its SHA-256.
3. `training/train.py` fine-tunes `EleutherAI/pythia-70m` on CPU using the teacher's JSON as the target sequence. At most the first 1,500 cleaned records are used. `validation.jsonl` is never used for training.
4. Weights are uploaded to SeaweedFS (`models/v1`, `models/v2`). The inference image does not contain them.
5. A FastAPI container in the `app` namespace downloads the selected model at startup. Traefik exposes `POST /parse`. An HPA, rolling update, and readiness probe cover Task 4.
6. `network/subnets.md` and `network/nacl.json` are the subnet plan and the stateless NACL for `10.20.0.0/16`.

Namespaces: `data` (SeaweedFS), `pipeline` (teacher workers), `app` (inference).

## Prerequisites (Arch Linux)

| Tool | Purpose |
|---|---|
| Docker | Images and k3d |
| k3d and kubectl | Local Kubernetes. This machine uses copies in `~/.local/bin`. |
| Ollama with `phi3.5` | Teacher. GPU acceleration is allowed. Training stays on CPU. |
| Python 3.12 | Training and tests. System Python 3.14 is not used for PyTorch. |
| make | The commands below |
| `uv` | Creates `.venv` |

```bash
# user-local tools used on this machine (no pacman transaction)
# k3d v5.8.3, kubectl, gitleaks, and Ollama were installed under ~/.local
export PATH="$HOME/.local/bin:$PATH"
```

Disk: the teacher weights are about 2.2 GB and each student checkpoint is a few hundred MB. This machine had more than 200 GB free.

Port 8080 is what `cluster/k3d.yaml` publishes for the marking command `locust --host http://localhost:8080`. If another process already owns 8080, `scripts/create_cluster.sh` applies the same file with host port 18080 and writes `results/port_override.txt`. Do not stop unrelated containers to free the port unless you intend to.

## Environment

```bash
cp .env.example .env
# edit AWS_SECRET_ACCESS_KEY if you want a different local SeaweedFS password
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python torch==2.4.1 --index-url https://download.pytorch.org/whl/cpu
uv pip install --python .venv/bin/python -r training/requirements.txt -r requirements/dev.txt
```

`.env` is gitignored. The cluster reads it into Kubernetes Secrets. Nothing in the image or the manifests hardcodes the secret.

## Teacher labelling

```bash
# Ollama on the laptop. Bind all interfaces so pods can use host.k3d.internal.
OLLAMA_HOST=0.0.0.0:11434 ollama serve
ollama pull phi3.5

# two workers at once, shard 0 and shard 1
bash scripts/label_local.sh

# or, after the cluster is up:
make label
make clean-data
```

`make clean-data` prints the count identity and writes `results/clean_counts.json` and `results/train.sha256`. Run it twice and compare the checksum.

## Training

```bash
make train SUBSET=50    # smoke test, first 50 records, still reads training/config.yaml
make train              # version v1, first 1,500 records, CPU
make train-v2           # version v2, seed and epoch count from config.yaml
```

Loss for each epoch is appended to `training/loss.csv` and copied to `results/loss_v1.csv` or `results/loss_v2.csv`. Checksums are `results/model_v1.sha256` and `results/model_v2.sha256`.

Publish `models/v1.tar.gz` (and v2) as assets of the GitHub Release `model-v1`. The SHA-256 in `models/v1/model.sha256` must match that asset.

## Model storage

SeaweedFS in namespace `data` exposes S3 on port 8333. `make up` creates buckets `datasets` and `models` and uploads `commands_pool.jsonl`. Training uploads `models/v1/` and `models/v2/` when `S3_ENDPOINT` is set. `scripts/seed_model.py` uploads a local checkpoint into the bucket.

## Docker

```bash
docker build -f service/Dockerfile -t cc3081/service:v1 .
docker image inspect cc3081/service:v1 --format '{{.Size}}'
```

Dependencies are pinned. The image is CPU-only and does not copy weights. The process runs as uid 1000.

## Kubernetes

```bash
cp .env.example .env
make up       # cluster from cluster/k3d.yaml, images, SeaweedFS, Deployment, Service, Ingress, HPA
make deploy   # re-apply manifests
make down     # k3d cluster delete cc3081 only
```

From a fresh clone the intended three commands are `cp .env.example .env`, `make up`, and `make train`. `make up` deploys the service. Pods stay unready until a model is present in the `models` bucket, because `/readyz` returns 503 until the download finishes.

Ingress path: `POST /parse`. Headers: `X-Model-Version`, `X-Served-By`.

## Tests

```bash
make lint
make test
python tools/nacl_sim.py network/nacl.json network/packets_sample.jsonl --check
make evaluate
```

`make evaluate` scores the teacher, the untrained Pythia-70M, and the trained student with `tools/score.py`. The teacher report is `results/teacher_validation.json`.

## Load test

```bash
uv pip install --python .venv/bin/python locust
make load
# equivalent marking command, with the host port this machine is actually using:
# locust -f tools/locustfile.py --headless --users 4 --spawn-rate 4 --run-time 2m --host http://localhost:8080 --csv results/loadtest
```

## Teardown

```bash
make down     # deletes only the cc3081 k3d cluster
make clean    # Python caches. Does not delete models, datasets, or other clusters.
```

Stop Ollama separately if you started it (`kill` the pid in `results/ollama_serve.pid`).

## Troubleshooting

- **8080 in use.** See `results/port_override.txt`. The marking file still says 8080.
- **Pods not Ready.** `/readyz` stays 503 until SeaweedFS has the model. Check `kubectl -n app logs deploy/command-parser`.
- **Teacher connection from a pod.** Ollama must listen on `0.0.0.0:11434`. The Job uses `http://host.k3d.internal:11434`.
- **Out of memory.** Do not run training, two inference replicas, and Ollama together. Stop the cluster with `k3d cluster stop cc3081` during the CPU fine-tune, then start it again.
- **Quality gate.** GitHub Actions job `quality` runs `score.py --min-validity 95`. Workflow dispatch input `model_source=base` evaluates untrained Pythia-70M and is expected to fail that gate.
- **Handwritten reflection.** `230101098.pdf` is not generated here. Notes for writing it are in `report/reflection_notes.md`.

## Layout

`cluster/` `prompts/` `worker/` `training/` `service/` `kubernetes/` `network/` `tests/` `results/` `docs/` `tools/` `data/` `.github/workflows/`
