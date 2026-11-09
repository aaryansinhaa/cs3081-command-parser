FROM python:3.12-slim

WORKDIR /app

COPY worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY worker/storage.py worker/worker.py worker/clean.py ./
COPY prompts/teacher_prompt.txt ./prompts/teacher_prompt.txt
COPY data/commands_pool.jsonl ./data/commands_pool.jsonl

ENV PROMPT_FILE=/app/prompts/teacher_prompt.txt \
    PYTHONUNBUFFERED=1

RUN useradd --create-home --uid 1000 appuser
USER appuser

ENTRYPOINT ["python", "worker.py"]
