import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "worker"))
import clean  # noqa: E402


def rec(rid, text, raw):
    return {"id": rid, "text": text, "teacher_raw": raw}


OK = '{"intent":"alarm_set","date":null,"time":"seven am","place":null}'


def test_rejection_precedence_partitions_the_input():
    records = [
        rec("C0001", "set an alarm for seven am", OK),
        rec("C0002", "bad json", "not json"),
        rec("C0003", "weather in london", '{"intent":"weather_query","date":null,"place":"london"}'),
        rec("C0004", "hello there", '{"intent":"nope","date":null,"time":null,"place":null}'),
        rec("C0005", "what time is it", '{"intent":"datetime_query","date":null,"time":null,"place":"paris"}'),
        rec("C0006", "set an alarm for seven am", OK),
    ]
    rows, counts = clean.clean_records(records)
    assert counts["input"] == 6
    assert counts["a"] == 1
    assert counts["b"] == 1
    assert counts["c"] == 1
    assert counts["d"] == 1
    assert counts["duplicates"] == 1
    assert counts["kept"] == 1
    assert counts["a"] + counts["b"] + counts["c"] + counts["d"] + counts["duplicates"] + counts["kept"] == counts["input"]
    assert rows[0]["id"] == "C0001"
    assert rows[0]["teacher_raw"] == OK
    assert rows[0]["text"] == "set an alarm for seven am"


def test_duplicate_keeps_smallest_id_and_sorts():
    records = [
        rec("C0009", "turn on the light", '{"intent":"calendar_set","date":null,"time":null,"place":null}'),
        rec("C0002", "turn on the light", '{"intent":"calendar_set","date":null,"time":null,"place":null}'),
        rec("C0005", "what is the weather in paris", '{"intent":"weather_query","date":null,"time":null,"place":"paris"}'),
    ]
    rows, counts = clean.clean_records(records)
    assert counts["duplicates"] == 1
    assert [row["id"] for row in rows] == ["C0002", "C0005"]


def test_invalid_slot_and_intent_are_distinct():
    assert clean.classify(rec("X", "alarm for seven am", OK))[0] == "keep"
    assert clean.classify(rec("X", "alarm for seven am",
        '{"intent":"alarm_set","date":null,"time":"eight pm","place":null}')) == "d"
    assert clean.classify(rec("X", "what time is it",
        '{"intent":"not_an_intent","date":null,"time":null,"place":null}')) == "c"


def test_jsonl_render_is_deterministic():
    records = [rec("C0002", "weather in london", '{"intent":"weather_query","date":null,"time":null,"place":"london"}')]
    rows, _ = clean.clean_records(records)
    first = clean.render_jsonl(rows)
    second = clean.render_jsonl(rows)
    assert first == second
    assert clean.sha256_text(first) == clean.sha256_text(second)
    json.loads(first)
