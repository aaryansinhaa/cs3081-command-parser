import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "service"))
os.environ["SKIP_MODEL_LOAD"] = "1"
os.environ.setdefault("MODEL_VERSION", "test")

import model_runner  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402


def test_validate_accepts_exact_schema():
    raw = '{"intent":"alarm_set","date":"tomorrow","time":"seven am","place":null}'
    obj = model_runner.validate(raw)
    assert obj["intent"] == "alarm_set"
    assert obj["place"] is None


def test_validate_rejects_bad_intent_and_extra_key():
    assert model_runner.validate('{"intent":"fly","date":null,"time":null,"place":null}') is None
    assert model_runner.validate('{"intent":"alarm_set","date":null,"time":null,"place":null,"extra":1}') is None
    assert model_runner.validate("not json") is None
    assert model_runner.validate('{"intent":"alarm_set","date":null,"time":1,"place":null}') is None


def test_fault_inject_returns_exact_error_body():
    main.runner.ready = True
    main.runner.raw_output = lambda text: '{"intent":"alarm_set","date":null,"time":null,"place":null}'
    os.environ["FAULT_INJECT"] = "1"
    client = TestClient(main.app)
    response = client.post("/parse", json={"text": "set an alarm"})
    assert response.status_code == 500
    assert response.json() == {"error": "invalid_model_output"}
    assert response.headers["X-Model-Version"] == "test"
    assert response.headers["X-Served-By"]
    os.environ.pop("FAULT_INJECT", None)


def test_health_and_successful_parse():
    main.runner.ready = True
    main.runner.raw_output = lambda text: '{"intent":"weather_query","date":null,"time":null,"place":"london"}'
    client = TestClient(main.app)
    assert client.get("/healthz").status_code == 200
    main.runner.ready = False
    assert client.get("/readyz").status_code == 503
    main.runner.ready = True
    assert client.get("/readyz").status_code == 200
    response = client.post("/parse", json={"text": "weather in london"})
    assert response.status_code == 200
    assert response.json() == {"intent": "weather_query", "date": None, "time": None, "place": "london"}
    assert set(response.json()) == {"intent", "date", "time", "place"}
