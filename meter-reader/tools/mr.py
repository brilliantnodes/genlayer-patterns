#!/usr/bin/env python3
"""Command-line client for MeterReader on GenLayer Studio (studionet).

Test GEN only. MR_KEY is a throwaway Studio key; never use a key that holds
anything of value. MR_ADDRESS overrides the deployed address in deployment.json.

  python tools/mr.py deploy                         # deploy contracts/meter_reader.py
  python tools/mr.py register examples/<file>.json  # register a meter from a spec file
  python tools/mr.py read <meter_id> [slots]        # read the last finished window
  python tools/mr.py read-at <meter_id> <window_start_unix> <slots>
  python tools/mr.py share <reading_id> <target_per_slot>
  python tools/mr.py show <reading_id>
  python tools/mr.py meter <meter_id>
  python tools/mr.py latest
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
    if os.environ.get("MR_ADDRESS"):
        return os.environ["MR_ADDRESS"]
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
    """The method's return value, status and votes from a receipt."""
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
    key = os.environ.get("MR_KEY")
    c, acct = client(key)
    if not key:
        fund(c, acct.address, 10)
    return c, acct


def deploy():
    c, acct = actor()
    fund(c, acct.address, 10)
    code = (ROOT / "contracts" / "meter_reader.py").read_text()
    tx = c.deploy_contract(code=code)
    r = wait(c, tx)
    addr = r.get("to_address") or r.get("recipient")
    out = {"network": "studionet", "address": addr, "deploy_tx": tx, "status": r.get("status_name")}
    print(json.dumps(out, indent=2))
    return out


def register_args(spec: dict) -> list:
    return [
        spec["url"], spec["source_name"], spec["series_name"], spec["value_label"], spec["unit_family"],
        int(spec["slot_minutes"]), spec.get("unit_label", ""), int(spec.get("resolution", 1)), int(spec.get("publish_lag_minutes", 0)),
        int(spec.get("read_within_minutes", 60)),
    ]


def last_window(slot_minutes: int, slots: int, now: float | None = None) -> int:
    """Start of the most recent window that is open for reading now: it ends
    at least one full slot before the current time, on the slot grid."""
    now = int(now if now is not None else time.time())
    slot = slot_minutes * 60
    end = (now // slot) * slot - slot
    return end - slots * slot


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    cmd, rest = sys.argv[1], sys.argv[2:]
    if cmd == "deploy":
        deploy()
        return
    addr = deployed_address()
    if cmd in ("register", "read", "read-at"):
        c, acct = actor()
        if cmd == "register":
            tx, r = write(c, addr, "register_meter", register_args(json.loads(Path(rest[0]).read_text())), acct)
        else:
            if cmd == "read":
                m = read_view(c, addr, "get_meter", [rest[0]])
                slots = int(rest[1]) if len(rest) > 1 else 5
                start = last_window(int(m["slot_minutes"]), slots)
            else:
                start, slots = int(rest[1]), int(rest[2])
            tx, r = write(c, addr, "read", [rest[0], start, slots], acct)
        print(json.dumps({"tx": tx, "status": r["status"], "votes": r["votes"], "result": r["result"]}, indent=2, default=str))
        return
    c, _ = client()
    if cmd == "share":
        print(json.dumps(read_view(c, addr, "delivery_share_bp", [rest[0], rest[1]]), indent=2))
    elif cmd == "show":
        print(json.dumps(read_view(c, addr, "get_reading", [rest[0]]), indent=2, default=str))
    elif cmd == "meter":
        print(json.dumps(read_view(c, addr, "get_meter", [rest[0]]), indent=2, default=str))
    elif cmd == "latest":
        for r in read_view(c, addr, "get_latest_readings", [20]):
            print(r["id"], r["meter_id"], r["kind"], r["reason"], r["summary"].get("mean_all_slots", ""))


if __name__ == "__main__":
    main()
