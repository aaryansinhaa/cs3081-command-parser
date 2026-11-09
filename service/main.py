"""Command-parser inference service.

POST /parse   {"text": "..."} -> the four-key object, or 500 {"error": "invalid_model_output"}
GET  /healthz -> 200 while the process is alive
GET  /readyz  -> 503 until the model is loaded, then 200

Configuration: MODEL_URI, MODEL_VERSION, S3_ENDPOINT, MAX_NEW_TOKENS, FAULT_INJECT.
Storage credentials come from the environment (a Kubernetes Secret in the cluster).
"""
import os
import socket
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

import model_runner

MODEL_VERSION = os.environ.get("MODEL_VERSION", "unknown")
POD_NAME = os.environ.get("POD_NAME") or os.environ.get("HOSTNAME") or socket.gethostname()
runner = model_runner.Runner()


def _load():
    try:
        runner.load()
        print(f"model ready version={MODEL_VERSION}", flush=True)
    except Exception as exc:
        print(f"model load failed: {exc}", flush=True)


@asynccontextmanager
async def lifespan(_app):
    if os.environ.get("SKIP_MODEL_LOAD") == "1":
        runner.ready = True
    else:
        threading.Thread(target=_load, daemon=True).start()
    yield


app = FastAPI(title="command-parser", lifespan=lifespan)


class ParseIn(BaseModel):
    text: str


def _headers():
    return {"X-Model-Version": MODEL_VERSION, "X-Served-By": POD_NAME}


@app.get("/healthz")
def healthz():
    return Response(status_code=200)


@app.get("/readyz")
def readyz():
    return Response(status_code=200 if runner.ready else 503)


@app.post("/parse")
def parse(body: ParseIn):
    if not runner.ready:
        return JSONResponse({"error": "not_ready"}, status_code=503, headers=_headers())
    raw = runner.raw_output(body.text)
    if os.environ.get("FAULT_INJECT") == "1":
        raw = "not json"
    obj = model_runner.validate(raw)
    if obj is None:
        return JSONResponse({"error": "invalid_model_output"}, status_code=500, headers=_headers())
    return JSONResponse(obj, status_code=200, headers=_headers())
