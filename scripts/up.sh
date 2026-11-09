#!/usr/bin/env bash
# Cluster, images, object storage, and the inference Deployment.
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="${HOME}/.local/bin:${PATH}"
[ -f .env ] || { echo "Copy .env.example to .env first."; exit 1; }

bash scripts/create_cluster.sh
docker build -f service/Dockerfile -t cc3081/service:v1 .
docker build -f worker/Dockerfile -t cc3081/worker:v1 .
k3d image import cc3081/service:v1 cc3081/worker:v1 -c cc3081
bash scripts/deploy.sh
port="$(cat results/ingress_port.txt 2>/dev/null || echo 8080)"
echo "up complete. Ingress: http://localhost:${port}/parse"
