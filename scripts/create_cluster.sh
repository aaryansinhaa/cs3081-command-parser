#!/usr/bin/env bash
# Create the k3d cluster from cluster/k3d.yaml.
# If host port 8080 is already taken by an unrelated process, the same file is applied
# with only the host port changed, and the override is recorded in results/port_override.txt.
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="${HOME}/.local/bin:${PATH}"
mkdir -p results
CLUSTER=cc3081

if k3d cluster list | awk 'NR>1 {print $1}' | grep -qx "$CLUSTER"; then
  echo "cluster $CLUSTER already exists"
  exit 0
fi

cfg=cluster/k3d.yaml
port=8080
if ss -tln | awk '{print $4}' | grep -Eq '(^|:)8080$'; then
  port=18080
  cfg="$(mktemp)"
  sed 's/8080:80/18080:80/' cluster/k3d.yaml > "$cfg"
  {
    echo "Host port 8080 was already in use, so this machine created the cluster from cluster/k3d.yaml with the host port set to 18080."
    echo "The committed cluster/k3d.yaml still maps 8080, which is the port the marking command uses on a free machine."
    ss -tlnp | grep 8080 || true
  } | tee results/port_override.txt
fi
echo "$port" > results/ingress_port.txt
k3d cluster create --config "$cfg"
