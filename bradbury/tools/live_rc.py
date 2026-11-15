"""RuleCheck and ListingGateExample live cases on Testnet Bradbury Phase 2 (GenVM v0.6 builds).

    cd bradbury/tools && BRADBURY_KEY_FILE=<throwaway key file> ../../venv/bin/python live_rc.py

Same fictional cases as on Studio: the two templates, four checks (Controlcoin
supported, Examplecoin contradicted, a missing explorer page undetermined,
Saltmarsh Pool status), then the consumer gate (template 1, 6-hour limit)
admitting, refusing and asking for a recheck, and refusing a check from
template 2 and a reused check on chain.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from live_mr import node, tx_row, deploy, write, read, BUILD  # noqa: E402

EX = Path(__file__).resolve().parents[2] / "rule-check" / "examples"
OUT = Path(__file__).resolve().parent.parent / "results" / "rule-check.json"
CHECKS = [("check-controlcoin", "1"), ("check-examplecoin", "1"), ("check-missing-explorer", "1"), ("check-saltmarsh-status", "2")]


def template_args(t):
    return [t["name"], json.dumps(t["pages"]), json.dumps(t["facts"]), json.dumps(t["rules"]), t.get("default_verdict", "undetermined")]


def main():
    out = {"network": "testnet-bradbury-phase-2", "chain_id": 4221, "build": "rule_check.v6.py", "templates": [], "checks": [], "gate": {}, "decisions": [], "refused": []}
    dep = deploy(BUILD / "rule_check.v6.py", [])
    addr = out["address"] = dep["address"]
    out["deploy"] = dep
    for f in ("template-launch-no-premine", "template-pool-status"):
        row = write(addr, "create_template", template_args(json.loads((EX / f"{f}.json").read_text())))
        row["template_id"] = str(read(addr, "get_counts")["templates"])
        row["file"] = f
        out["templates"].append(row)
    for f, tid in CHECKS:
        spec = json.loads((EX / f"{f}.json").read_text())
        row = write(addr, "check", [tid, json.dumps(spec["urls"]), spec.get("subject", "")])
        cid = str(read(addr, "get_counts")["checks"])
        c = read(addr, "get_check", [cid])
        row.update({"example": f, "template_id": tid, "check_id": cid, "verdict": c.get("verdict"), "rule": c.get("rule"),
                    "deciding_facts": c.get("deciding_facts"), "subject": c.get("subject")})
        out["checks"].append(row)
        print("check", {k: row[k] for k in ("example", "check_id", "verdict", "rule")}, flush=True)
        OUT.write_text(json.dumps(out, indent=2, default=str) + "\n")
    g = deploy(BUILD / "listing_gate.v6.py", [addr, "1", '["supported"]', '["contradicted"]', 6])
    gate = g["address"]
    out["gate"] = {"address": gate, "deploy": g, "config": read(gate, "get_config")}
    for chk, expect in zip(out["checks"][:3], ("ADMIT", "REFUSE", "RECHECK")):
        subject = chk["subject"] if expect == "ADMIT" else ""
        row = write(gate, "decide", [chk["check_id"], subject])
        n = read(gate, "get_count")
        d = read(gate, "get_decision", [str(n)])
        row.update({"example": chk["example"], "check_id": chk["check_id"], "expected": expect, "decision": d.get("decision"), "verdict": d.get("verdict"), "rule": d.get("rule")})
        out["decisions"].append(row)
        print("decision", {k: row[k] for k in ("example", "expected", "decision")}, flush=True)
    for label, cid in (("check from template 2 (pool status)", out["checks"][3]["check_id"]), ("same check used twice", out["checks"][0]["check_id"])):
        row = write(gate, "decide", [cid, ""])
        row.update({"case": label, "check_id": cid, "gate_count_after": read(gate, "get_count")})
        out["refused"].append(row)
        print("refused", {k: row[k] for k in ("case", "execution", "gate_count_after")}, flush=True)
    out["counts"] = read(addr, "get_counts")
    out["gate_count"] = read(gate, "get_count")
    OUT.write_text(json.dumps(out, indent=2, default=str) + "\n")
    print("done", out["counts"], out["gate_count"], flush=True)


if __name__ == "__main__":
    main()
