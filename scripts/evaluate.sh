#!/usr/bin/env bash
# Score the teacher, the untrained Pythia-70M, and the trained student on validation.jsonl.
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-python3}"
if [ -x .venv/bin/python ]; then PYTHON=.venv/bin/python; fi
mkdir -p results

if [ ! -f results/pred_teacher.jsonl ]; then
  "$PYTHON" scripts/eval_teacher.py
fi
"$PYTHON" tools/score.py results/pred_teacher.jsonl data/validation.jsonl --out results/teacher_validation.json

"$PYTHON" training/predict.py --model EleutherAI/pythia-70m --input data/validation.jsonl --out results/pred_base.jsonl
"$PYTHON" tools/score.py results/pred_base.jsonl data/validation.jsonl --out results/score_base.json

if [ -d models/v1 ]; then
  "$PYTHON" training/predict.py --model models/v1 --input data/validation.jsonl --out results/pred_student_v1.jsonl
  "$PYTHON" tools/score.py results/pred_student_v1.jsonl data/validation.jsonl --out results/score_student_v1.json
fi
if [ -d models/v2 ]; then
  "$PYTHON" training/predict.py --model models/v2 --input data/validation.jsonl --out results/pred_student_v2.jsonl
  "$PYTHON" tools/score.py results/pred_student_v2.jsonl data/validation.jsonl --out results/score_student_v2.json
fi
echo "evaluation reports are in results/"
