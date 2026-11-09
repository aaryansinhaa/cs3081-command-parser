import ipaddress
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import subnet_calc  # noqa: E402


def test_allocation_matches_the_handout_rules():
    rows = subnet_calc.main()
    expected = [
        ("app", "10.20.0.0/22", 1022),
        ("public", "10.20.4.0/24", 254),
        ("data", "10.20.5.0/25", 126),
        ("management", "10.20.5.128/27", 30),
    ]
    assert len(rows) == 4
    previous_end = None
    for (name, hosts, network, usable), (ename, ecidr, eusable) in zip(rows, expected):
        assert name == ename
        assert str(network) == ecidr
        assert usable == eusable
        assert usable >= hosts
        if previous_end is not None:
            assert int(network.network_address) == previous_end + 1
        previous_end = int(network.broadcast_address)
        assert network.subnet_of(ipaddress.ip_network("10.20.0.0/16"))
