"""Estimate the cost of 1,000 requests from student_kit rate_card.json and a measured rps."""
import argparse
import json


def cost_per_thousand(rate, replicas, cpu_limit, mem_gib, rps):
    per_replica_hour = cpu_limit * rate["vcpu_hour"] + mem_gib * rate["gib_memory_hour"]
    hourly = per_replica_hour * replicas
    requests_per_hour = rps * 3600.0
    if requests_per_hour <= 0:
        raise SystemExit("rps must be positive")
    return {
        "currency": rate["currency"],
        "vcpu_hour": rate["vcpu_hour"],
        "gib_memory_hour": rate["gib_memory_hour"],
        "replicas": replicas,
        "cpu_limit": cpu_limit,
        "mem_gib": mem_gib,
        "per_replica_hour": per_replica_hour,
        "hourly_all_replicas": hourly,
        "rps": rps,
        "requests_per_hour": requests_per_hour,
        "cost_per_1000": hourly * 1000.0 / requests_per_hour,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rate-card", default="data/rate_card.json")
    parser.add_argument("--replicas", type=int, required=True)
    parser.add_argument("--cpu-limit", type=float, required=True)
    parser.add_argument("--mem-gib", type=float, required=True)
    parser.add_argument("--rps", type=float, required=True)
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    rate = json.load(open(args.rate_card, encoding="utf-8"))
    result = cost_per_thousand(rate, args.replicas, args.cpu_limit, args.mem_gib, args.rps)
    lines = [
        f"currency: {result['currency']}",
        f"vcpu_hour: {result['vcpu_hour']}",
        f"gib_memory_hour: {result['gib_memory_hour']}",
        f"replicas: {result['replicas']}",
        f"cpu_limit per replica: {result['cpu_limit']}",
        f"memory GiB per replica: {result['mem_gib']}",
        f"cost per replica-hour: {result['per_replica_hour']:.4f}",
        f"hourly cost of all replicas: {result['hourly_all_replicas']:.4f}",
        f"measured rps: {result['rps']}",
        f"requests per hour: {result['requests_per_hour']:.4f}",
        f"cost per 1000 requests: {result['cost_per_1000']:.6f}",
    ]
    text = "\n".join(lines) + "\n"
    print(text, end="")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text)


if __name__ == "__main__":
    main()
