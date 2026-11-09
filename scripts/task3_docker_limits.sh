#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
set -a
# shellcheck disable=SC1091
[ -f .env ] && . ./.env
set +a
mkdir -p results

# Run service against local model dir (no cluster required for the 50-request limit test).
docker run -d --name cc3081-task3-test --rm \
  --cpus 1 --memory 1g \
  -e MODEL_URI=file:///model \
  -e MODEL_VERSION=v1-local \
  -e MAX_NEW_TOKENS=64 \
  -v "$(pwd)/models/v1:/model:ro" \
  -p 18000:8000 \
  cc3081/service:v1

cleanup() { docker rm -f cc3081-task3-test 2>/dev/null || true; }
trap cleanup EXIT

for i in $(seq 1 60); do
  curl -sf http://127.0.0.1:18000/readyz >/dev/null && break
  sleep 2
done

echo "50 sequential requests at 1 CPU, 1 GiB" | tee results/task3_docker_limits.txt
peak=""
for n in $(seq 1 50); do
  curl -sf -X POST http://127.0.0.1:18000/parse \
    -H 'Content-Type: application/json' \
    -d '{"text":"set alarm for seven am tomorrow"}' >/dev/null
  if [ $((n % 10)) -eq 0 ]; then
    mem="$(docker stats cc3081-task3-test --no-stream --format '{{.MemUsage}}' 2>/dev/null || true)"
    echo "after $n requests mem=$mem" | tee -a results/task3_docker_limits.txt
  fi
done
docker stats cc3081-task3-test --no-stream | tee -a results/task3_docker_limits.txt
docker inspect cc3081-task3-test --format 'OOMKilled={{.State.OOMKilled}}' | tee -a results/task3_docker_limits.txt
echo "done" | tee -a results/task3_docker_limits.txt
