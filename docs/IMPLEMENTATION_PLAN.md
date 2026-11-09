# Implementation plan

Student: Aaryan Kumar Sinha, roll number 230101098.  
Course: Cloud Computing (CS3081).  
Title: Knowledge Distillation and Deployment of a Lightweight Command-Parsing Language Model on a Local Cloud.

This plan is the Phase 0 record. Status values are updated as evidence is collected. A file existing is not the same as a task being verified.

## Sources, in priority order

1. `CLOUD_ASSIGNMENT_DESCRIPTION.pdf` (15 pages). This is the marking source.
2. `cloud_assignment/`, the official student kit: `data/`, `tools/score.py`, `tools/locustfile.py`, `tools/nacl_sim.py`, `network/packets_sample.jsonl`.
3. Official documentation for k3d, SeaweedFS, Kubernetes, Transformers, and Ollama.
4. `230101032/230101032/`, a friend's completed project. It was read as a reference and was not copied as this submission. Its `results/` are that student's measurements and are not reused.

## Machine

| Item | Observed |
|---|---|
| OS | Arch Linux, kernel 6.18 |
| CPU | 12th Gen Intel i5-12500H, 16 threads |
| RAM | 15 GiB, about 7.6 GiB available while other Docker containers are running |
| Disk | 234 GiB free on `/` |
| GPU | NVIDIA GeForce RTX 3050 Laptop, 4096 MiB. Driver responds outside the sandbox. |
| Python | System 3.14.9. Training uses CPython 3.12 from `uv` because the pinned CPU PyTorch wheel targets 3.12. |
| Docker | 29.9.3, daemon running. The user is in the `docker` group. |
| GitHub | `gh` is logged in as `aaryansinhaa`. |
| Port 8080 | Already bound by the unrelated container `shiksha-nginx-prod`. The committed `cluster/k3d.yaml` still maps 8080. Local cluster creation records an override to 18080 when 8080 is busy. |

Installed into `~/.local/bin` (no system package changes): k3d v5.8.3, kubectl v1.37.2, gitleaks 8.24.2. Ollama is installed the same way.

Student training stays on CPU. Ollama may use the GPU for the fixed teacher (`phi3.5`, temperature 0, seed 42).

## Architecture

```
commands_pool.jsonl
        |  two workers, line_number % SHARD_COUNT == SHARD_INDEX
        v
Ollama phi3.5  --->  datasets/teacher/shard-*.jsonl
        |
        v
worker/clean.py  --->  datasets/v1/train.jsonl + train.sha256
        |
        v
CPU fine-tune of EleutherAI/pythia-70m  --->  models/v1 and models/v2
        |
        v
SeaweedFS buckets datasets, models  (namespace data)
        |
        v
FastAPI /parse  (namespace app, model downloaded at startup)
        |
        v
Traefik Ingress, HPA, rolling update, recovery, Locust
```

Namespaces: `data`, `pipeline`, `app`. Cluster name: `cc3081`, one k3s server, no agent, because 16 GiB is shared with other containers.

## Task status

| Task | Marks | Status |
|---|---:|---|
| 1 Object storage and teacher labelling | 12 | Done: cluster, SeaweedFS, 3000 labels, 2 indexed pipeline pods, clean checksum stable. |
| 2 Student training and distillation | 20 | Done: v1/v2 trained, evaluate three-way, v2 99% JSON validity on validation. |
| 3 Inference container | 14 | Done: image 1.66GB, FAULT_INJECT 500, 50-req docker limit test. |
| 4 Kubernetes deployment | 22 | Done: deploy/ingress/HPA, cold start, rollout/rollback, recovery (see results/). |
| 5 Subnetting and NACL | 10 | Done: 6/6 sample packets, subnet calc. |
| 6 Reproducibility and CI | 10 | Repo push + Release + Actions pending in FINAL_AUDIT after `gh` steps. |
| 7 Performance, cost, review | 12 | Done: Locust CSV, cost.txt, top_pods; high error rate under laptop CPU load documented. |

## Marking checklist

| Criterion | Implementation | Command | Evidence |
|---|---|---|---|
| Cluster from `cluster/k3d.yaml`, SeaweedFS in `data` | `cluster/k3d.yaml`, `kubernetes/seaweedfs/seaweedfs.yaml` | `make up` | `results/deploy_status.txt` |
| Buckets and `commands_pool.jsonl` | `scripts/init_storage.py` | `make deploy` | command output in `results/` |
| Teacher prompt | `prompts/teacher_prompt.txt` | inspected in the repo | file itself |
| Two pipeline workers, distinct shards | `worker/worker.py`, `kubernetes/pipeline/worker-job.yaml` | `make label` or `scripts/label_local.sh` | worker logs, shard files |
| Every id in exactly one shard | `worker.assigned` | `pytest tests/test_shard.py`, `clean.py` coverage | `results/clean_counts.json` |
| `clean.py` checksum | `worker/clean.py` | `make clean-data` twice | `results/train.sha256` |
| Count identity | `clean_records` | `pytest tests/test_clean.py` | `results/clean_counts.json` |
| `config.yaml` six items | `training/config.yaml` | `make train` | file and `training/loss.csv` |
| `make train SUBSET=50` | `training/train.py` | `make train SUBSET=50` | log in `results/` |
| models v1 and v2 in object storage | `scripts/seed_model.py` | after training | S3 listing |
| Release checksum | `models/v1/model.sha256` | `gh release` | `results/model_v1.sha256` |
| Three-way evaluation | `scripts/evaluate.sh`, `tools/score.py` | `make evaluate` | `results/teacher_validation.json` and score files |
| Hidden-test claims | none until a hidden set exists | — | not claimed |
| `/parse`, `/healthz`, `/readyz`, headers, fault injection | `service/main.py` | `pytest tests/test_validate.py` | test output and later curl logs |
| Image pins, size, no weights | `service/Dockerfile` | `docker build` | `results/image_size.txt` |
| 50 requests at 1 CPU / 1 GiB | docker run limits | recorded in `results/` | command output |
| Ingress, probes, HPA, rollout, recovery, cold start, balance | `kubernetes/app/` | runbook commands | `results/` |
| Subnets | `network/subnets.md` | `python scripts/subnet_calc.py` | `results/subnet_calc.txt` |
| NACL | `network/nacl.json` | `python tools/nacl_sim.py ... --check` | `results/nacl_sample.txt` |
| `make up` / `make down` | `Makefile`, `scripts/up.sh` | those targets | command logs |
| CI lint, tests, release eval, 95% gate | `.github/workflows/ci.yml` | GitHub Actions | run URL, including one deliberate failure |
| Secret scan and `AI_USE.md` | gitleaks, `AI_USE.md` | `gitleaks detect` | `results/gitleaks.txt` |
| Locust p50, p95, rps, errors, kubectl top, cold start | `tools/locustfile.py` | `make load` | `results/loadtest_*` |
| Cost and SLO | `scripts/cost.py`, `data/rate_card.json` | after the load test | `results/cost.txt` |

## Execution order

1. Finish the Ollama install and `ollama pull phi3.5`.
2. Run two local labelling workers immediately. Upload the shards once SeaweedFS is up, then run the indexed Job in `pipeline` so the same worker code executes in the cluster. The worker resumes completed ids, so the cluster job does not repeat finished calls.
3. Bring up k3d and SeaweedFS while labelling runs. Do not start the two 1 GiB inference pods until the model exists.
4. Clean the shards, verify the checksum twice, train v1 and v2 on CPU.
5. Build the service image, load it into k3d, deploy, and collect Task 3 and Task 4 evidence.
6. Run the standard Locust command, cost, and SLO.
7. Push the repository, publish the model release, and run the quality-gate workflow once on the untrained model and once on the release.
8. Write `report/report.pdf` from the measured files only.
9. Package `230101098.zip` after the handwritten reflection `230101098.pdf` is present.

## Hardware limits that change the schedule

- Teacher labelling of 3,000 commands is the long pole. It starts before the cluster so the GPU is not idle during image pulls.
- Training, the cluster, and Ollama should not all be at full load together. Available RAM is about 7.6 GiB.
- Port 8080 stays mapped in `cluster/k3d.yaml` for marking. This laptop uses 18080 until the unrelated container releases 8080.
- The `final` Git tag is not created until the implementation has been checked and you approve it.
- `230101098.pdf` must be your handwritten scan. A draft for that reflection is in `report/reflection_notes.md`. It is not a substitute for the scan.

## Rejection precedence for cleaning

A record is counted once, in this order: (a) invalid JSON, (b) keys are not exactly the four required names, (c) intent not in the eight allowed values, (d) a slot is neither null nor text that appears in the command, (e) duplicate command text, keeping the smallest id. The identity `input = a + b + c + d + duplicates + kept` is asserted in `tests/test_clean.py` and printed by `worker/clean.py`.
