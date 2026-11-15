"""MeterReader live cases on GenLayer Testnet Bradbury Phase 2 (GenVM v0.6 build).

    cd bradbury/tools && BRADBURY_KEY_FILE=<throwaway key file> ../../venv/bin/python live_mr.py

Same fictional cases as meter-reader/tools/live_cases.py on Studio: five meters,
the last five finished minutes of each, the rig-dark page read inside its down
period, shares against 10 GH/s, and the consumer contract recording a share on
chain. Writes go through genlayer-js 2.0.0-rc.2 (js2/gl.mjs); results are read
back with the contracts' views, because Bradbury receipts carry no return value.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "meter-reader" / "tools"))
import mr  # noqa: E402  (register_args, last_window only; no Studio calls)

HERE = Path(__file__).resolve().parent
JS = HERE
BUILD = HERE.parent / "build"
EX = Path(__file__).resolve().parents[2] / "meter-reader" / "examples"
OUT = HERE.parent / "results" / "meter-reader.json"
TARGET = str(10 * 10**9)
EXAMPLES = ["fernhollow-rig-sixty", "fernhollow-rig-steady", "fernhollow-rig-gappy", "fernhollow-rig-ghost", "quillmoor-rig-dark"]


def node(*args, tries=3):
    for i in range(tries):
        p = subprocess.run(["node", "gl.mjs", *args], cwd=JS, capture_output=True, text=True, timeout=1500)
        line = [l for l in p.stdout.splitlines() if l.startswith("{")]
        d = json.loads(line[-1]) if line else {"ok": False, "error": p.stderr[-500:]}
        if d.get("ok") or args[0] in ("deploy", "write"):
            return d
        time.sleep(8)
    return d


def tx_row(d):
    raw = d.get("raw") or {}
    lr = raw.get("lastRound") or {}
    return {"tx": d.get("hash"), "result": raw.get("resultName"), "execution": raw.get("txExecutionResultName"),
            "votes_revealed": lr.get("votesRevealed"), "validators": lr.get("validatorsCount"), "secs": d.get("secs"), "error": d.get("error")}


def deploy(path, args):
    d = node("deploy", str(path), json.dumps(args))
    row = tx_row(d)
    row["address"] = (d.get("raw") or {}).get("recipient")
    print("deploy", path.name, row, flush=True)
    if row["execution"] != "FINISHED_WITH_RETURN":
        raise SystemExit(f"deploy failed: {row}")
    return row


def write(addr, fn, args):
    d = node("write", addr, fn, json.dumps(args))
    row = tx_row(d)
    print("write", fn, row, flush=True)
    return row


def read(addr, fn, args=None):
    d = node("read", addr, fn, json.dumps(args or []))
    if not d.get("ok"):
        raise RuntimeError(f"read {fn} failed: {d.get('error')}")
    return d["result"]


def main():
    out = {"network": "testnet-bradbury-phase-2", "chain_id": 4221, "build": "meter_reader.v6.py", "meters": [], "readings": [], "consumer": {}}
    dep = deploy(BUILD / "meter_reader.v6.py", [])
    addr = out["address"] = dep["address"]
    out["deploy"] = dep
    for name in EXAMPLES:
        spec = json.loads((EX / f"{name}.json").read_text())
        row = write(addr, "register_meter", mr.register_args(spec))
        row["meter_id"] = str(read(addr, "get_counts")["meters"])
        row["example"] = name
        out["meters"].append(row)
    for m in out["meters"]:
        start = mr.last_window(1, 5)
        row = write(addr, "read", [m["meter_id"], start, 5])
        rid = str(read(addr, "get_counts")["readings"])
        res = read(addr, "get_reading", [rid])
        row.update({"example": m["example"], "meter_id": m["meter_id"], "reading_id": rid, "kind": res.get("kind"), "reason": res.get("reason"),
                    "values": [x.get("value") for x in res.get("table", [])]})
        if res.get("kind") != "NO_READING":
            row["share_bp"] = read(addr, "delivery_share_bp", [rid, TARGET]).get("share_bp")
        out["readings"].append(row)
        print("reading", {k: row[k] for k in ("example", "kind", "reason", "share_bp") if k in row}, flush=True)
        OUT.write_text(json.dumps(out, indent=2, default=str) + "\n")
    dark = out["meters"][-1]["meter_id"]
    while True:
        t = time.gmtime()
        if t.tm_min % 10 == 6 and t.tm_sec < 30:
            break
        time.sleep(10)
    row = write(addr, "read", [dark, mr.last_window(1, 5), 5])
    rid = str(read(addr, "get_counts")["readings"])
    res = read(addr, "get_reading", [rid])
    row.update({"example": "quillmoor-rig-dark (down period)", "meter_id": dark, "reading_id": rid, "kind": res.get("kind"), "reason": res.get("reason"), "values": []})
    out["readings"].append(row)
    print("dark", {k: row[k] for k in ("kind", "reason")}, flush=True)
    cdep = deploy(BUILD / "meter_consumer.v6.py", [addr])
    first = out["readings"][0]["reading_id"]
    rec = write(cdep["address"], "record_share", [first, TARGET])
    out["consumer"] = {"address": cdep["address"], "deploy": cdep, "record": rec, "count": read(cdep["address"], "get_count"),
                       "record_1": read(cdep["address"], "get_record", ["1"])}
    out["counts"] = read(addr, "get_counts")
    OUT.write_text(json.dumps(out, indent=2, default=str) + "\n")
    print("done", out["counts"], out["consumer"]["record_1"], flush=True)


if __name__ == "__main__":
    main()
