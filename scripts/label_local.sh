#!/usr/bin/env bash
# Two local teacher workers with different shard indexes. Safe to re-run; completed ids are skipped.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p results datasets/teacher
export PATH="${HOME}/.local/bin:${PATH}"
export OLLAMA_HOST="${OLLAMA_HOST:-http://127.0.0.1:11434}"
export TEACHER_MODEL=phi3.5
export TEACHER_TEMPERATURE=0
export TEACHER_SEED=42
export TEACHER_NUM_CTX=1536
export SHARD_COUNT=2
PY="${PYTHON:-python3}"
SHARD_INDEX=0 "$PY" worker/worker.py > results/worker-shard-0.log 2>&1 &
p0=$!
SHARD_INDEX=1 "$PY" worker/worker.py > results/worker-shard-1.log 2>&1 &
p1=$!
echo "local workers pid $p0 $p1"
set +e
wait "$p0"
s0=$?
wait "$p1"
s1=$?
set -e
echo "shard 0 exit $s0; shard 1 exit $s1"
exit $((s0 || s1))
