"""Allocate 10.20.0.0/16 into the four required subnets and print the table.

Largest requirement first, each block placed immediately after the previous one,
smallest prefix whose usable-host count (2^(32-prefix) - 2) meets the requirement.
"""
import ipaddress

REQUIREMENTS = [
    ("app", 1000),
    ("public", 250),
    ("data", 100),
    ("management", 20),
]
START = ipaddress.ip_address("10.20.0.0")
PARENT = ipaddress.ip_network("10.20.0.0/16")


def smallest_prefix(hosts):
    for prefix in range(32, 0, -1):
        usable = (1 << (32 - prefix)) - 2
        if usable >= hosts:
            return prefix, usable
    raise RuntimeError(hosts)


def main():
    cursor = int(START)
    rows = []
    for name, hosts in REQUIREMENTS:
        prefix, usable = smallest_prefix(hosts)
        block = 1 << (32 - prefix)
        if cursor % block != 0:
            raise SystemExit(f"{name} start {cursor} is not aligned to /{prefix}")
        network = ipaddress.ip_network((cursor, prefix))
        if network.network_address < PARENT.network_address or network.broadcast_address > PARENT.broadcast_address:
            raise SystemExit(f"{name} does not fit in {PARENT}")
        rows.append((name, hosts, network, usable))
        cursor = int(network.broadcast_address) + 1

    print("| Subnet | Needed | Prefix | Network | Usable range | Broadcast | Usable hosts |")
    print("|---|---:|---|---|---|---|---:|")
    for name, hosts, network, usable in rows:
        first = network.network_address + 1
        last = network.broadcast_address - 1
        print(
            f"| {name} | {hosts} | /{network.prefixlen} | {network.network_address} "
            f"| {first} – {last} | {network.broadcast_address} | {usable} |"
        )
    return rows


if __name__ == "__main__":
    main()
