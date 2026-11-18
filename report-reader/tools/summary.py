#!/usr/bin/env python3
"""Print a live run's record as a Markdown table for the README.

    python tools/summary.py examples/live-studio-s1.json
"""
import json
import sys

EXPL = {"studio": "https://explorer-studio.genlayer.com", "bradbury": "https://scan.bradbury.genlayer.com"}


def outcome(s):
    r = s.get("result")
    base = f"{s.get('status')} / {s.get('execution')}"
    if isinstance(r, dict):
        if "figures" in r and r.get("kind") == "READ":
            return base + " · READ " + ", ".join(f"{k} {v}" for k, v in r["figures"].items())
        if r.get("kind") in ("NO_READING", "NOT_PUBLISHED", "CLOSED"):
            return base + " · " + r["kind"] + (" " + r.get("reason", "") if r.get("reason") else "") + (" → " + r["status"] if r.get("status") else "")
        if "missing" in r:
            return base + f" · missing {r['missing']}"
        if "error" in r:
            return base + " · " + r["error"]
        if "deal" in r and isinstance(r["deal"], dict) and r["deal"].get("result"):
            d = r["deal"]["result"]
            return base + f" · {d['status']}: seller {int(d['to_seller']) / 1e18:g} GEN, buyer {int(d['to_buyer']) / 1e18:g} GEN"
        if "deal" in r:
            return base + " · escrowed " + str(int(r["deal"]["amount"]) / 1e18) + " GEN"
        if "amount" in r:
            return base + f" · withdrew {int(r['amount']) / 1e18:g} GEN"
        if r.get("id") and r.get("digest"):
            return base + f" · report {r['id']}"
    elif isinstance(r, str) and r:
        return base + " · " + r
    return base


def main():
    rec = json.loads(open(sys.argv[1]).read())
    ex = EXPL[rec["net"]]
    print("| # | Case | Call | Outcome | Tx |")
    print("|---|---|---|---|---|")
    for i, s in enumerate(rec["steps"], 1):
        tx = f"[`{s['tx'][:10]}…`]({ex}/tx/{s['tx']})" if s.get("tx") else ""
        print(f"| {i} | {s['case']} | `{s['fn']}` | {outcome(s)} | {tx} |")


if __name__ == "__main__":
    main()
