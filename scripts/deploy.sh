#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="${HOME}/.local/bin:${PATH}"
set -a
# shellcheck disable=SC1091
. ./.env
set +a
PYTHON="${PYTHON:-python3}"
if [ -x .venv/bin/python ]; then
  PYTHON=.venv/bin/python
fi

kubectl apply -f kubernetes/namespaces.yaml
bash scripts/create_secrets.sh
kubectl apply -f kubernetes/seaweedfs/seaweedfs.yaml
kubectl -n data rollout status deploy/seaweedfs --timeout=180s

seed_once() {
  kubectl -n data port-forward --address 127.0.0.1 svc/seaweedfs 8333:8333 >>results/seaweed-port-forward.log 2>&1 &
  local pf=$!
  trap 'kill "$pf" 2>/dev/null || true' RETURN
  for _ in $(seq 1 60); do
    curl -sf http://127.0.0.1:8333/status >/dev/null 2>&1 && break
    sleep 1
  done
  if ! curl -sf http://127.0.0.1:8333/status >/dev/null 2>&1; then
    echo "Seaweed S3 not reachable on 127.0.0.1:8333" >&2
    return 1
  fi
  S3_ENDPOINT=http://127.0.0.1:8333 "$PYTHON" scripts/init_storage.py || return 1
  if [ -d models/v1 ] || [ -d models/v2 ]; then
    S3_ENDPOINT=http://127.0.0.1:8333 "$PYTHON" scripts/seed_model.py || return 1
  else
    echo "models/v1 is not on disk yet. make train will upload it."
  fi
  return 0
}

mkdir -p results
ok=0
for attempt in 1 2 3 4 5; do
  if seed_once; then ok=1; break; fi
  echo "seed attempt $attempt failed" >&2
  sleep 2
done
[ "$ok" = 1 ]

kubectl apply -f kubernetes/app/deployment.yaml -f kubernetes/app/service.yaml -f kubernetes/app/ingress.yaml -f kubernetes/app/hpa.yaml
kubectl -n app rollout status deploy/command-parser --timeout=300s || true
kubectl -n app get deploy,svc,ingress,hpa,pods -o wide | tee results/deploy_status.txt
