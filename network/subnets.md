# Task 5 — Subnetting and stateless network access control

Address block: `10.20.0.0/16`.

Subnets are allocated from the largest host requirement to the smallest. The first subnet starts at `10.20.0.0`. Each following subnet starts at the address immediately after the previous broadcast address. The prefix is the smallest one whose usable-host count, `2^(32 - prefix) - 2`, covers the requirement. The arithmetic is produced by `scripts/subnet_calc.py`.

| Order | Subnet | Hosts needed | Prefix | Block size | Network address | Usable host range | Broadcast address | Usable hosts |
|---|---|---:|---|---:|---|---|---|---:|
| 1 | app | 1,000 | /22 | 1,024 | 10.20.0.0 | 10.20.0.1 – 10.20.3.254 | 10.20.3.255 | 1,022 |
| 2 | public | 250 | /24 | 256 | 10.20.4.0 | 10.20.4.1 – 10.20.4.254 | 10.20.4.255 | 254 |
| 3 | data | 100 | /25 | 128 | 10.20.5.0 | 10.20.5.1 – 10.20.5.126 | 10.20.5.127 | 126 |
| 4 | management | 20 | /27 | 32 | 10.20.5.128 | 10.20.5.129 – 10.20.5.158 | 10.20.5.159 | 30 |

Why each prefix is the smallest that fits:

- app needs 1,000 hosts. A /23 has 510 usable hosts, which is too small. A /22 has 1,022.
- public needs 250 hosts. A /25 has 126 usable hosts, which is too small. A /24 has 254.
- data needs 100 hosts. A /26 has 62 usable hosts, which is too small. A /25 has 126.
- management needs 20 hosts. A /28 has 14 usable hosts, which is too small. A /27 has 30.

Contiguous placement inside `10.20.0.0/16`:

```
10.20.0.0/22    app          10.20.0.0   .. 10.20.3.255
10.20.4.0/24    public       10.20.4.0   .. 10.20.4.255
10.20.5.0/25    data         10.20.5.0   .. 10.20.5.127
10.20.5.128/27  management   10.20.5.128 .. 10.20.5.159
```

The next free address is `10.20.5.160`. The four blocks do not overlap, each starts on a valid prefix boundary, and all of them fit in `10.20.0.0/16`.

## NACL for the public subnet

The load balancer lives in `public` (`10.20.4.0/24`). Rules are in `network/nacl.json`. They are evaluated from the lowest rule number upward. The first match wins. If nothing matches, the packet is denied. Clients use ephemeral ports 1024–65535.

### Inbound

| Rule | Protocol | Ports | Source | Action | Purpose |
|---:|---|---|---|---|---|
| 100 | all | all | 198.51.100.0/24 | deny | Block the abusive range on every port, including 80 and 443. |
| 110 | tcp | 80 | 0.0.0.0/0 | allow | HTTP from anywhere. |
| 120 | tcp | 443 | 0.0.0.0/0 | allow | HTTPS from anywhere. |
| 130 | tcp | 22 | 10.20.5.128/27 | allow | SSH only from the management subnet. |
| 140 | tcp | 1024–65535 | 10.20.0.0/22 | allow | Replies from the app subnet, arriving on the load balancer's ephemeral ports. |

### Outbound

| Rule | Protocol | Ports | Destination | Action | Purpose |
|---:|---|---|---|---|---|
| 100 | tcp | 8000 | 10.20.0.0/22 | allow | Forward parser traffic to the app subnet. |
| 110 | tcp | 1024–65535 | 0.0.0.0/0 | allow | Replies to clients on their ephemeral ports. |

Checked with the supplied simulator:

```bash
python tools/nacl_sim.py network/nacl.json network/packets_sample.jsonl --check
```

## Why a stateless NACL needs reply rules, and why order matters

A NACL does not remember a connection. Allowing an outbound request to the app subnet on TCP 8000 does not automatically allow the app subnet's reply. That reply is a separate inbound packet, addressed to an ephemeral port on the load balancer, so it needs its own inbound rule (rule 140). The load balancer's replies to external clients likewise need an explicit outbound rule (rule 110) for ephemeral ports. Without those two rules, one direction of the conversation is dropped.

Rule order matters because the first match wins. TCP 80 and TCP 443 are allowed from `0.0.0.0/0`, which includes `198.51.100.0/24`. The deny for that range is rule 100, a lower number than rules 110 and 120, so a packet from the abusive range is denied before the broader web allows are considered. If the deny had a higher number, a packet such as HTTPS from `198.51.100.9` would already have matched an allow and the deny would never be reached.
