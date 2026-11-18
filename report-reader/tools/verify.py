#!/usr/bin/env python3
"""Check a Studio live-run record against the chain, after every transaction
has finalized, and write the result next to it as <record>-check.json.

    python tools/verify.py examples/live-studio-s1.json

For every recorded transaction it re-reads the transaction from the chain and
compares its status and execution result with the record. Then it reads the
contracts' views and balances again: the consumer's balance must equal
locked + credited (withdrawals are paid as messages when their transaction
finalizes, so balances read before that can still include them).
"""
import json
import sys
from pathlib import Path

from genlayer_py import create_account, create_client
from genlayer_py.chains import studionet

EXEC = {"SUCCESS": ("SUCCESS", "FINISHED_WITH_RETURN"), "ERROR": ("ERROR", "FINISHED_WITH_ERROR")}


def main():
    path = Path(sys.argv[1])
    rec = json.loads(path.read_text())
    c = create_client(chain=studionet, account=create_account())
    rpc = lambda m, p: c.provider.make_request(method=m, params=p)["result"]  # noqa: E731
    rows, ok = [], True
    for s in rec["steps"]:
        if not s.get("tx"):
            continue
        t = rpc("eth_getTransactionByHash", [s["tx"]])
        lr = ((t.get("consensus_data") or {}).get("leader_receipt") or [{}])
        lr = lr[0] if isinstance(lr, list) and lr else (lr or {})
        chain_exec = lr.get("execution_result")
        match = chain_exec == s.get("execution") and t.get("status") in ("ACCEPTED", "FINALIZED")
        votes = (t.get("consensus_data") or {}).get("votes") or {}
        ok &= match
        rows.append({"case": s["case"], "fn": s["fn"], "tx": s["tx"], "status": t.get("status"), "result": t.get("result_name"),
                     "execution": chain_exec, "recorded_execution": s.get("execution"), "votes": votes, "match": match})
    out = {"record": path.name, "transactions": len(rows), "all_match": ok, "rows": rows}
    if "contracts" in rec:  # ReportReader run
        cons = rec["contracts"]["consumer"]["address"]
        reader = rec["contracts"]["reader"]["address"]
        totals = c.read_contract(address=cons, function_name="totals", args=[])
        bal = int(rpc("eth_getBalance", [cons, "latest"]), 16)
        out["reader_counts"] = c.read_contract(address=reader, function_name="get_counts", args=[])
        out["consumer_totals"] = totals
        out["consumer_balance"] = str(bal)
        out["balance_reconciles"] = bal == int(totals["locked"]) + int(totals["credited"])
        out["accounts"] = {r: str(int(rpc("eth_getBalance", [a, "latest"]), 16)) for r, a in rec["accounts"].items()}
    else:  # ClaimEscrow run
        addr = rec["contract"]["address"]
        totals = c.read_contract(address=addr, function_name="totals", args=[])
        bal = int(rpc("eth_getBalance", [addr, "latest"]), 16)
        out["totals"] = totals
        out["balance"] = str(bal)
        out["balance_reconciles"] = bal == int(totals["locked"]) + int(totals["credited"])
    check = path.with_name(path.stem + "-check.json")
    check.write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=1))
    bad = [r for r in rows if not r["match"]]
    if bad:
        print("MISMATCH:", json.dumps(bad, indent=1)[:2000])


if __name__ == "__main__":
    main()
