#!/usr/bin/env bash
# Collect marking evidence for Tasks 3, 4, and 7. Run from repo root with cluster up.
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="${HOME}/.local/bin:${PATH}"
mkdir -p results
HOST_PORT="${HOST_PORT:-8080}"
if [ -f results/ingress_port.txt ]; then
  p="$(tr -d ' \n' < results/ingress_port.txt)"
  [ -n "$p" ] && HOST_PORT="$p"
fi
HOST="http://localhost:${HOST_PORT}"
PYTHON="${PYTHON:-.venv/bin/python}"
if [ ! -x "$PYTHON" ]; then
  PYTHON="python3"
fi
SITE="/home/aaryan/Projects/cloud_comp/230101098/.venv/lib/python3.12/site-packages"
PYBIN="/home/aaryan/.local/share/uv/python/cpython-3.12.13-linux-x86_64-gnu/bin/python3.12"
run_py() {
  PYTHONPATH="$SITE" "$PYBIN" "$@"
}

echo "=== Task 3: image size ===" | tee results/task3_header.txt
docker images cc3081/service:v1 --format '{{.Size}}' | tee results/image_size.txt

echo "=== Task 3: fault inject ===" | tee -a results/task3_fault.txt
kubectl -n app scale deploy/command-parser --replicas=1
kubectl -n app set env deploy/command-parser FAULT_INJECT="1"
kubectl -n app rollout status deploy/command-parser --timeout=300s
kubectl -n app wait --for=condition=ready pod -l app=command-parser --timeout=120s
sleep 3
code="$(curl -s -o results/fault_body.json -w '%{http_code}' -X POST "$HOST/parse" \
  -H 'Content-Type: application/json' -d '{"text":"set alarm for seven am"}')"
echo "FAULT_INJECT http_code=$code body=$(cat results/fault_body.json)" | tee -a results/task3_fault.txt
kubectl -n app set env deploy/command-parser FAULT_INJECT-
kubectl -n app rollout status deploy/command-parser --timeout=300s

echo "=== ensure v1, 2 replicas for Task 4 baseline ==="
kubectl -n app set env deploy/command-parser MODEL_URI=s3://models/v1 MODEL_VERSION=v1
kubectl -n app scale deploy/command-parser --replicas=2
kubectl -n app rollout status deploy/command-parser --timeout=600s
kubectl -n app wait --for=condition=ready pod -l app=command-parser --timeout=300s

echo "=== Task 4: cold start x3 ===" | tee results/coldstart.txt
for i in 1 2 3; do
  kubectl -n app delete pod -l app=command-parser --wait=false || true
  sleep 3
  start=$(date +%s)
  kubectl -n app rollout status deploy/command-parser --timeout=600s
  kubectl -n app get pods -l app=command-parser -o jsonpath='{.items[*].status.conditions[?(@.type=="Ready")].status}' | grep -q True
  elapsed=$(( $(date +%s) - start ))
  echo "run $i cold start: ${elapsed}s" | tee -a results/coldstart.txt
done
kubectl -n app logs -l app=command-parser --tail=30 | tee results/coldstart_logs.txt

echo "=== Task 4+7: load test (2 replicas) ==="
kubectl -n app scale deploy/command-parser --replicas=2
kubectl -n app rollout status deploy/command-parser --timeout=300s
run_py -m locust -f tools/locustfile.py --headless --users 4 --spawn-rate 4 --run-time 2m \
  --host "$HOST" --csv results/loadtest 2>&1 | tee results/loadtest_run.txt

kubectl -n app top pods 2>&1 | tee results/top_pods.txt || echo "metrics-server unavailable" | tee results/top_pods.txt

RPS="$(awk -F, '/POST \/parse/ && NR>1 {print $10; exit}' results/loadtest_stats.csv 2>/dev/null || echo 2)"
run_py scripts/cost.py --replicas 2 --cpu-limit 1 --mem-gib 1 --rps "$RPS" | tee results/cost.txt

echo "=== Task 4: HPA scale test ===" | tee results/hpa_scale.txt
kubectl -n app scale deploy/command-parser --replicas=1
kubectl -n app autoscale deploy/command-parser --min=1 --max=2 --cpu-percent=70 2>/dev/null || true
kubectl -n app get hpa | tee -a results/hpa_scale.txt
run_py -m locust -f tools/locustfile.py --headless --users 4 --spawn-rate 4 --run-time 90s \
  --host "$HOST" --csv results/hpa_load 2>&1 | tee -a results/hpa_scale.txt &
LOC_PID=$!
sleep 15
kubectl -n app get hpa -w 2>&1 | head -20 | tee -a results/hpa_watch.txt &
wait "$LOC_PID" || true
kubectl -n app scale deploy/command-parser --replicas=2

echo "=== Task 4: rollout v1->v2 under load ===" | tee results/rollout.txt
LOADTEST_HEADERS_OUT=results/rollout_headers.json \
run_py -m locust -f tools/locustfile.py --headless --users 4 --spawn-rate 4 --run-time 4m \
  --host "$HOST" --csv results/rollout 2>&1 | tee -a results/rollout.txt &
LOC_PID=$!
sleep 10
kubectl -n app set env deploy/command-parser MODEL_URI=s3://models/v2 MODEL_VERSION=v2
kubectl -n app rollout status deploy/command-parser --timeout=600s
sleep 5
kubectl -n app rollout undo deploy/command-parser
kubectl -n app rollout status deploy/command-parser --timeout=600s
wait "$LOC_PID" || true
[ -f results/rollout_headers.json ] && cp -f results/rollout_headers.json results/rollout_headers_copy.json
cat results/rollout_stats.csv 2>/dev/null | tee results/rollout_stats_summary.txt

echo "=== Task 4: recovery (delete one pod under load) ===" | tee results/recovery.txt
run_py -m locust -f tools/locustfile.py --headless --users 4 --spawn-rate 4 --run-time 2m \
  --host "$HOST" --csv results/recovery 2>&1 | tee -a results/recovery.txt &
LOC_PID=$!
sleep 5
kubectl -n app delete pod "$(kubectl -n app get pod -l app=command-parser -o name | head -1)" --wait=false
kubectl -n app get pods -w 2>&1 | head -25 | tee -a results/recovery.txt &
wait "$LOC_PID" || true

kubectl -n app get deploy,svc,ingress,hpa,pods -o wide | tee results/deploy_status_final.txt
echo "evidence collection done"
