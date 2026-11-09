import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "worker"))
import worker  # noqa: E402


def test_every_line_belongs_to_exactly_one_shard():
    count = 2
    owners = []
    for line in range(3000):
        hits = [index for index in range(count) if worker.assigned(line, count, index)]
        assert hits == [line % count]
        owners.append(hits[0])
    assert owners.count(0) == 1500
    assert owners.count(1) == 1500


def test_shard_index_zero_gets_even_lines():
    assert worker.assigned(0, 2, 0)
    assert not worker.assigned(1, 2, 0)
    assert worker.assigned(1, 2, 1)
