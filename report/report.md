# CS3081 Mini Project Report

**Student:** Aaryan Kumar Sinha  
**Roll:** 230101098  
**Repository:** https://github.com/aaryansinhaa/cs3081-command-parser  
**Cluster:** k3d `cc3081`, Ingress `http://localhost:8080`

---

## Task 1 — Object storage and teacher labelling

k3d cluster from `cluster/k3d.yaml`, SeaweedFS in namespace `data`, buckets `datasets` and `models`. Teacher prompt in `prompts/teacher_prompt.txt`; Ollama `phi3.5`, temperature 0, seed 42.

Two indexed Job pods in `pipeline` (`teacher-label-0`, `teacher-label-1`) with `SHARD_INDEX` 0 and 1 (`results/task1_workers.txt`). Shards uploaded to `datasets/teacher/shard-*.jsonl`.

| Stage | Count |
|-------|------:|
| Input | 3000 |
| (a) invalid JSON | 0 |
| (b) bad keys | 1 |
| (c) bad intent | 0 |
| (d) bad slot | 144 |
| Duplicates | 45 |
| Kept | 2810 |

Checksum `a473bda6210f4550bc538e98d2ae58b5ed82f3c68c1a340dd34f4b81793c83a2` stable across two `make clean-data` runs (`results/clean_counts.json`).

**Sharding:** line number `n` goes to worker `w` when `n % SHARD_COUNT == SHARD_INDEX`.

---

## Task 2 — Student training

`training/config.yaml` records seed, LR, batch, epochs, max_seq_len, library versions. `make train` uses first 1500 cleaned rows; v2 uses seed 7 and 4 epochs.

| Model | json_validity | full_frame |
|-------|--------------:|-----------:|
| Teacher | 100.0% | 44.0% |
| Base Pythia-70m | 0.0% | 0.0% |
| Student v1 | 84.0% | 33.0% |
| Student v2 | 99.0% | 46.0% |

Release asset `v1.tar.gz` checksum matches `models/v1/model.sha256` (`300e8d9b…`).

**Distillation (short):** Sequence-level training matches the teacher’s generated JSON string. Logit-based KD would need teacher logits at each token; our teacher is external (Ollama) and not differentiable into the student. Limitation: slot errors remain when the teacher or student copies phrases incorrectly.

---

## Task 3 — Container

Image `cc3081/service:v1` size **1.66GB** (`results/image_size.txt`). No weights in image; model fetched from S3 at startup. `FAULT_INJECT=1` → HTTP 500 `{"error":"invalid_model_output"}` (`results/task3_fault.txt`).

50 sequential requests at **1 CPU, 1 GiB** peak **~403 MiB**, no OOM (`results/task3_docker_limits.txt`).

---

## Task 4 — Kubernetes

Deployment (2 replicas, limits 1 CPU / 1 GiB), Service, Ingress `/parse`, HPA min 1 max 2 @ 70% CPU. Rolling update v1→v2 under load, then `kubectl rollout undo` (`results/rollout.txt`, `results/rollout_headers.json`). Recovery: pod delete under load (`results/recovery.txt`).

**Cold start (median of 3):** 12 s (`results/coldstart.txt`); logs show S3 download (`results/coldstart_logs.txt`).

**Limitation:** Single k3d node — no multi-machine fault tolerance.

Load-balancing header counts during rollout mixed replicas; dedicated 2-replica run in `results/loadtest_headers.json` after stabilising on v1.

---

## Task 5 — Networking

Subnet plan and NACL in `network/subnets.md`, `network/nacl.json`. Sample packets **6/6** (`results/nacl_sample.txt`).

Stateless NACL: return traffic needs explicit allow rules; deny on `198.51.100.0/24` must appear before broader allows on the same ports.

---

## Task 6 — CI and reproducibility

`make up` / `make down`, Makefile, `pytest` (≥3 tests), `.github/workflows/ci.yml` (lint, gitleaks, tests, Release eval, 95% gate). Gitleaks: no leaks (`results/gitleaks.txt`). Failed gate run URL: *(fill after `workflow_dispatch` with `base`)*.

`AI_USE.md` documents AI assistance and manual verification.

---

## Task 7 — Performance and cost

Primary load test (`results/loadtest_stats.csv`, 2 min, 4 users):

| Metric | Value |
|--------|------:|
| Requests | 176 |
| Failures | 30 (17.0%) |
| p50 | 2800 ms |
| p95 | 7900 ms |
| Throughput | 1.49 req/s |

`kubectl top pods` → `results/top_pods.txt`. Cost estimate → `results/cost.txt` (≈ **1.47 INR / 1000 requests** at measured RPS).

**SLO:** 99% success over one 2-minute Locust run (176 requests). Budget = 1.76 failures allowed; used 30 (CPU saturation on laptop during concurrent rollouts — see limitation).

### Review table

| Component | Evidence | Limitation | Improvement |
|-----------|----------|------------|-------------|
| Data/storage | 2810 train rows; checksum stable | Large shard uploads via port-forward | In-cluster seed Job only |
| Model quality | v2 99% JSON validity | Slots still wrong ~54% of time | Constrained decoding |
| Latency/throughput | p50 2.8s, 1.49 rps | p95 > 5s under load | GPU inference or smaller model |
| Resource use | ~400 MiB / 1 GiB limit | Single node shares CPU | Dedicated inference node |
| Reliability | Recovery + rollback tested | 17% errors during heavy tests | Rollout during low load |
| Security/cost | NACL 6/6; 1.47 INR/1k req | Secrets in k8s only | Rotate S3 keys |

---

## References

Assignment kit `score.py`, `locustfile.py`, `nacl_sim.py`; HuggingFace Pythia-70m; k3d; SeaweedFS docs.
