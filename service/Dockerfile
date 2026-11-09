# CPU-only inference image. Model weights are downloaded at startup, not copied here.
FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir torch==2.4.1 --index-url https://download.pytorch.org/whl/cpu

COPY service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY service/main.py service/model_runner.py ./
COPY data/schema.json ./schema.json

ENV PYTHONUNBUFFERED=1 \
    MAX_NEW_TOKENS=64 \
    TORCH_NUM_THREADS=1 \
    HF_HUB_DISABLE_TELEMETRY=1 \
    SCHEMA_PATH=/app/schema.json

EXPOSE 8000

RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /tmp/model \
    && chown -R appuser:appuser /app /tmp
USER appuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
