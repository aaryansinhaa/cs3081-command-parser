# AI use

Student: Aaryan Kumar Sinha, roll number 230101098.

## Tools

Cursor, with the model Grok 4.7, was used to inspect the official handout and student kit, compare them with a reference repository, and draft the project code, tests, manifests, and this file.

No paid model API was used for teacher labels or for inference. Teacher replies come from local Ollama running `phi3.5`. The student model is `EleutherAI/pythia-70m`, trained locally on CPU.

## What the assistant produced

- Repository layout, worker, cleaner, training script, FastAPI service, Dockerfiles, Kubernetes manifests, subnet and NACL files, Makefile, GitHub Actions workflow, and tests.
- The teacher prompt text in `prompts/teacher_prompt.txt`.

## How the output was checked

- The handout PDF and the student-kit scripts were read before the code was written. The friend's repository was treated as a secondary reference. Its result files were not copied.
- `tools/nacl_sim.py` was executed on `network/nacl.json`. The sample score is recorded in `results/nacl_sample.txt`.
- Subnet addresses were calculated by `scripts/subnet_calc.py` and checked against the usable-host formula.
- Unit tests cover sharding, cleaning, schema validation, fault injection, and the subnet table.
- Training loss, `score.py` reports, Locust numbers, pod measurements, and workflow URLs are written only after the corresponding command has been run. Missing runs are marked as not verified rather than filled in.

## What was not delegated

The handwritten reflection `230101098.pdf` is written and scanned by the student. The assistant only prepared `report/reflection_notes.md` as notes for that writing.
