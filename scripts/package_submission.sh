#!/usr/bin/env bash
# Build 230101098.zip for the course submission portal.
# The archive root is 230101098/. Model weights, virtualenvs, and .git are excluded.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
NAME="230101098"
ZIP="${ROOT}/../${NAME}.zip"
fail=0

need() {
  if [ ! -e "$1" ]; then
    echo "MISSING: $1"
    fail=1
  fi
}

need README.md
need AI_USE.md
need Makefile
need prompts/teacher_prompt.txt
need worker/worker.py
need worker/clean.py
need training/config.yaml
need training/train.py
need service/main.py
need service/Dockerfile
need cluster/k3d.yaml
need kubernetes/namespaces.yaml
need kubernetes/seaweedfs/seaweedfs.yaml
need kubernetes/app/deployment.yaml
need kubernetes/app/ingress.yaml
need kubernetes/app/hpa.yaml
need network/subnets.md
need network/nacl.json
need .github/workflows/ci.yml
need report/report.pdf
need 230101098.pdf
need data/commands_pool.jsonl
need data/validation.jsonl
need tools/score.py
need tools/nacl_sim.py
need tools/locustfile.py

if ! grep -q 'https://github.com/aaryansinhaa/cs3081-command-parser' README.md; then
  echo "MISSING: GitHub URL in README.md"
  fail=1
fi

if [ -f 230101098.pdf ]; then
  pages="$(pdfinfo 230101098.pdf 2>/dev/null | awk '/Pages:/ {print $2}')"
  echo "reflection pages: ${pages:-unknown}"
  if [ -n "${pages:-}" ] && [ "$pages" -gt 3 ]; then
    echo "REFLECTION HAS MORE THAN 3 PAGES"
    fail=1
  fi
fi

if [ -f report/report.pdf ]; then
  pages="$(pdfinfo report/report.pdf 2>/dev/null | awk '/Pages:/ {print $2}')"
  echo "report pages: ${pages:-unknown}"
fi

# Evidence expected after execution. Warn, do not drop the archive, so a partial run is visible.
for ev in results/nacl_sample.txt results/subnet_calc.txt results/clean_counts.json results/train.sha256 \
          results/teacher_validation.json training/loss.csv results/loadtest_stats.csv; do
  if [ ! -e "$ev" ]; then
    echo "WARNING: evidence not present yet: $ev"
  fi
done

if grep -RInE 'AKIA[0-9A-Z]{16}|BEGIN (RSA |OPENSSH )?PRIVATE KEY' --exclude-dir=.venv --exclude-dir=.git --exclude='*.zip' . >/tmp/secret-scan.txt 2>/dev/null; then
  echo "POSSIBLE SECRET:"
  cat /tmp/secret-scan.txt
  fail=1
fi

if [ "$fail" != 0 ]; then
  echo "packaging checks failed"
  exit 1
fi

stage="$(mktemp -d)"
mkdir -p "$stage/$NAME"
tar -C "$ROOT" \
  --exclude='.git' \
  --exclude='.venv' \
  --exclude='__pycache__' \
  --exclude='.pytest_cache' \
  --exclude='.ruff_cache' \
  --exclude='models' \
  --exclude='datasets' \
  --exclude='.env' \
  -cf - . | tar -C "$stage/$NAME" -xf -
rm -f "$ZIP"
(cd "$stage" && zip -r -q "$ZIP" "$NAME")
rm -rf "$stage"
echo "wrote $ZIP"
unzip -t "$ZIP" >/tmp/zip-test.txt
echo "zip test: $(tail -n 1 /tmp/zip-test.txt)"
echo "size: $(du -h "$ZIP" | awk '{print $1}')"
echo "top entries:"
unzip -l "$ZIP" | awk 'NR>3 {print}' | head -n 40
echo "required paths:"
for p in "$NAME/README.md" "$NAME/AI_USE.md" "$NAME/Makefile" "$NAME/230101098.pdf" \
         "$NAME/report/report.pdf" "$NAME/service/Dockerfile" "$NAME/.github/workflows/ci.yml" \
         "$NAME/network/nacl.json" "$NAME/prompts/teacher_prompt.txt"; do
  unzip -l "$ZIP" | grep -q "$p" && echo "  ok $p" || { echo "  MISSING IN ZIP $p"; exit 1; }
done
