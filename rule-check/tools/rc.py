#!/usr/bin/env python3
"""Command-line client for RuleCheck on GenLayer Studio (studionet).

Test GEN only. RC_KEY is a throwaway Studio key; never use a key that holds
anything of value. RC_ADDRESS overrides the deployed address in deployment.json.

  python tools/rc.py deploy                              # deploy contracts/rule_check.py
  python tools/rc.py template examples/template-<x>.json # store a template
  python tools/rc.py check <template_id> examples/check-<x>.json
  python tools/rc.py show <check_id>
  python tools/rc.py tpl <template_id>
  python tools/rc.py latest
"""
import json
import os
import sys
import time
from pathlib import Path

from genlayer_py import create_account, create_client
from genlayer_py.chains import studionet
from genlayer_py.types import TransactionStatus

ROOT = Path(__file__).resolve().parents[1]
DEPLOYMENT = ROOT / "deployment.json"
G = 10**18


def deployed_address() -> str:
    if os.environ.get("RC_ADDRESS"):
        return os.environ["RC_ADDRESS"]
    try:
        return json.loads(DEPLOYMENT.read_text())["address"]
    except Exception:
        return ""


def client(key=None):
    acct = create_account(key) if key else create_account()
    return create_client(chain=studionet, account=acct), acct


def fund(c, address, gen=100):
    """Studio's built-in faucet (sim_fundAccount)."""
    return c.provider.make_request(method="sim_fundAccount", params=[address, gen * G])


def wait(c, tx, status=TransactionStatus.ACCEPTED, retries=200):
    """Wait for a receipt. Studio's gateway sometimes answers 502 for a few
    seconds; that is retried instead of treated as a failure."""
    deadline = time.time() + retries * 3
    last = None
    while time.time() < deadline:
        try:
            return c.wait_for_transaction_receipt(transaction_hash=tx, status=status, interval=3000, retries=20)
        except Exception as e:  # gateway error or still pending
            last = e
            time.sleep(5)
    raise RuntimeError(f"no receipt for {tx}: {last}")


def receipt_result(r):
    cd = r.get("consensus_data") or {}
    lr = cd.get("leader_receipt")
    lr = lr[0] if isinstance(lr, list) and lr else lr
    lr = lr if isinstance(lr, dict) else {}
    res = lr.get("result") or {}
    payload = res.get("payload") if isinstance(res, dict) else None
    if isinstance(payload, dict) and "readable" in payload:
        try:
            payload = json.loads(payload["readable"])
        except Exception:
            payload = payload["readable"]
    return {"status": r.get("status_name"), "execution": lr.get("execution_result"), "result": payload, "votes": cd.get("votes")}


def write(c, address, fn, args, acct=None):
    tx = None
    for attempt in range(3):
        try:
            tx = c.write_contract(address=address, function_name=fn, args=args, value=0, account=acct)
            break
        except Exception:
            if attempt == 2:
                raise
            time.sleep(5)
    return tx, receipt_result(wait(c, tx))


def read_view(c, address, fn, args=None):
    for attempt in range(5):
        try:
            return c.read_contract(address=address, function_name=fn, args=args or [])
        except Exception:
            if attempt == 4:
                raise
            time.sleep(4)


def actor():
    key = os.environ.get("RC_KEY")
    c, acct = client(key)
    if not key:
        fund(c, acct.address, 10)
    return c, acct


def deploy():
    c, acct = actor()
    fund(c, acct.address, 10)
    tx = c.deploy_contract(code=(ROOT / "contracts" / "rule_check.py").read_text())
    r = wait(c, tx)
    out = {"network": "studionet", "address": r.get("to_address") or r.get("recipient"), "deploy_tx": tx, "status": r.get("status_name")}
    print(json.dumps(out, indent=2))
    return out


def template_args(t: dict) -> list:
    return [t["name"], json.dumps(t["pages"]), json.dumps(t["facts"]), json.dumps(t["rules"]), t.get("default_verdict", "undetermined")]


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd, rest = sys.argv[1], sys.argv[2:]
    if cmd == "deploy":
        deploy()
        return
    addr = deployed_address()
    if cmd in ("template", "check"):
        c, acct = actor()
        if cmd == "template":
            tx, r = write(c, addr, "create_template", template_args(json.loads(Path(rest[0]).read_text())), acct)
        else:
            spec = json.loads(Path(rest[1]).read_text())
            tx, r = write(c, addr, "check", [rest[0], json.dumps(spec["urls"]), spec.get("subject", "")], acct)
        print(json.dumps({"tx": tx, "status": r["status"], "votes": r["votes"], "result": r["result"]}, indent=2, default=str))
        return
    c, _ = client()
    if cmd == "show":
        print(json.dumps(read_view(c, addr, "get_check", [rest[0]]), indent=2))
    elif cmd == "tpl":
        print(json.dumps(read_view(c, addr, "get_template", [rest[0]]), indent=2))
    elif cmd == "latest":
        for x in read_view(c, addr, "get_latest_checks", [20]):
            print(x["id"], x["template_id"], x["verdict"], x["rule"], x["subject"])


if __name__ == "__main__":
    main()
