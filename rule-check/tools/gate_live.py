#!/usr/bin/env python3
"""Live proof of ListingGateExample on GenLayer Studio.

    cd rule-check && ../venv/bin/python tools/gate_live.py

1. Runs three fresh RuleCheck checks with template 1 ("no premine"):
   Controlcoin (supported), Examplecoin (contradicted), and Controlcoin with
   a missing explorer page (undetermined).
2. Deploys examples/consumer/listing_gate_example.py pointed at RuleCheck,
   trusting template 1, admitting on "supported", refusing on
   "contradicted", and accepting checks up to 6 hours old.
3. Asks the gate to decide on each fresh check (ADMIT, REFUSE, RECHECK), then
   shows three uses the gate refuses: a check from template 2, a check older
   than 6 hours (check 2, from 14 Nov), and a check used a second time.

Writes examples/consumer/live-runs.json. Fictional coins and pages only;
throwaway Studio accounts with test GEN.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rc  # noqa: E402

ROOT = rc.ROOT
OUT = ROOT / "examples" / "consumer" / "live-runs.json"
CHECKS = [("check-controlcoin", "ADMIT"), ("check-examplecoin", "REFUSE"), ("check-missing-explorer", "RECHECK")]


def agree(votes) -> int:
    return sum(1 for v in (votes or {}).values() if v == "agree")


def main():
    c, acct = rc.actor()
    rc.fund(c, acct.address, 20)
    time.sleep(3)
    addr = rc.deployed_address()
    out = {"rule_check": addr, "template_id": "1", "checks": [], "gate": {}, "decisions": [], "refused": []}

    for name, _ in CHECKS:
        spec = json.loads((ROOT / "examples" / f"{name}.json").read_text())
        tx, r = rc.write(c, addr, "check", ["1", json.dumps(spec["urls"]), spec.get("subject", "")], acct)
        res = r["result"] if isinstance(r["result"], dict) else {}
        row = {"example": name, "tx": tx, "check_id": res.get("id"), "verdict": res.get("verdict"), "rule": res.get("rule"),
               "subject": res.get("subject"), "agree": agree(r["votes"]), "status": r["status"]}
        out["checks"].append(row)
        print("check", row, flush=True)

    code = (ROOT / "examples" / "consumer" / "listing_gate_example.py").read_text()
    dtx = c.deploy_contract(code=code, args=[addr, "1", '["supported"]', '["contradicted"]', 6])
    rd = rc.wait(c, dtx)
    gate = rd.get("to_address") or rd.get("recipient")
    out["gate"] = {"address": gate, "deploy_tx": dtx, "status": rd.get("status_name"), "config": rc.read_view(c, gate, "get_config")}
    print("gate", out["gate"], flush=True)

    for (name, expect), chk in zip(CHECKS, out["checks"]):
        subject = chk["subject"] if expect == "ADMIT" else ""
        tx, r = rc.write(c, gate, "decide", [chk["check_id"], subject], acct)
        res = r["result"] if isinstance(r["result"], dict) else {}
        row = {"example": name, "check_id": chk["check_id"], "expected": expect, "decision": res.get("decision"), "verdict": res.get("verdict"),
               "rule": res.get("rule"), "deciding_facts": res.get("deciding_facts"), "tx": tx, "status": r["status"], "execution": r["execution"]}
        out["decisions"].append(row)
        print("decision", row, flush=True)

    misuse = [
        ("check from template 2 (pool status)", "4"),
        ("check older than 6 hours (check 2, 14 Nov)", "2"),
        ("same check used twice", out["checks"][0]["check_id"]),
    ]
    for label, cid in misuse:
        try:
            tx, r = rc.write(c, gate, "decide", [cid, ""], acct)
            row = {"case": label, "check_id": cid, "tx": tx, "status": r["status"], "execution": r["execution"], "result": r["result"]}
        except Exception as e:
            row = {"case": label, "check_id": cid, "error": str(e)[:300]}
        out["refused"].append(row)
        print("refused", row, flush=True)

    out["count"] = rc.read_view(c, gate, "get_count")
    out["rule_check_counts"] = rc.read_view(c, addr, "get_counts")
    OUT.write_text(json.dumps(out, indent=2, default=str) + "\n")
    print("wrote", OUT, flush=True)


if __name__ == "__main__":
    main()
