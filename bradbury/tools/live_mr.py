"""MeterReader live cases on GenLayer Testnet Bradbury Phase 2 (GenVM v0.6 build).

    cd bradbury/tools && BRADBURY_KEY_FILE=<throwaway key file> ../../venv/bin/python live_mr.py

BRADBURY_JS names the folder holding gl.mjs with genlayer-js 2.0.0-rc.2 installed
(default: this folder). Same fictional cases as meter-reader/tools/live_cases.py on
Studio: five meters, the last five finished minutes of each, the rig-dark page read
inside its down period, a second read of an already-read window (refused: it has its
official reading), and the consumer contract pinning a window that has not started,
then settling from its official reading. Results are read back with the contracts'
views, because Bradbury receipts carry no return value; reads can trail writes, so
each id is taken only after the counter has moved.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "meter-reader" / "tools"))
import mr  # noqa: E402  (register_args, last_window only; no Studio calls)

HERE = Path(__file__).resolve().parent
JS = Path(os.environ.get("BRADBURY_JS", HERE))
BUILD = HERE.parent / "build"
EX = Path(__file__).resolve().parents[2] / "meter-reader" / "examples"
OUT = HERE.parent / "results" / "meter-reader.json"
TARGET = str(10 * 10**9)
EXAMPLES = ["fernhollow-rig-sixty", "fernhollow-rig-steady", "fernhollow-rig-gappy", "fernhollow-rig-ghost", "quillmoor-rig-dark"]


def node(*args, tries=3):
    for _ in range(tries):
        p = subprocess.run(["node", "gl.mjs", *args], cwd=JS, capture_output=True, text=True, timeout=1500)
        line = [ln for ln in p.stdout.splitlines() if ln.startswith("{")]
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


def counted(addr, key, before, tries=20):
    """The counter after a write, once the read node has caught up."""
    n = before
    for _ in range(tries):
        n = int(read(addr, "get_counts")[key])
        if n > before:
            return n
        time.sleep(6)
    return n


def main():
    out = {"network": "testnet-bradbury-phase-2", "chain_id": 4221, "build": "build/meter_reader.py", "meters": [], "readings": [], "consumer": {}}
    dep = deploy(BUILD / "meter_reader.py", [])
    addr = out["address"] = dep["address"]
    out["deploy"] = dep
    for name in EXAMPLES:
        spec = json.loads((EX / f"{name}.json").read_text())
        before = int(read(addr, "get_counts")["meters"])
        row = write(addr, "register_meter", mr.register_args(spec))
        row["meter_id"] = str(counted(addr, "meters", before))
        row["example"] = name
        out["meters"].append(row)

    def take(meter_id, start, label):
        before = int(read(addr, "get_counts")["readings"])
        row = write(addr, "read", [meter_id, start, 5])
        n = counted(addr, "readings", before)
        if n == before:
            row.update({"example": label, "meter_id": meter_id, "window_start": start, "kind": None, "note": "no reading stored"})
            return row
        res = read(addr, "get_reading", [str(n)])
        row.update({"example": label, "meter_id": meter_id, "reading_id": str(n), "window_start": start, "kind": res.get("kind"),
                    "reason": res.get("reason"), "values": [x.get("value") for x in res.get("table", [])]})
        if res.get("kind") != "NO_READING":
            row["share_bp"] = read(addr, "delivery_share_bp", [str(n), TARGET]).get("share_bp")
        return row

    for m in out["meters"]:
        row = take(m["meter_id"], mr.last_window(1, 5), m["example"])
        out["readings"].append(row)
        print("reading", {k: row.get(k) for k in ("example", "kind", "reason", "share_bp")}, flush=True)
        OUT.write_text(json.dumps(out, indent=2, default=str) + "\n")
    dark = out["meters"][-1]["meter_id"]
    while True:
        t = time.gmtime()
        if t.tm_min % 10 == 6 and t.tm_sec < 30:
            break
        time.sleep(10)
    row = take(dark, mr.last_window(1, 5), "quillmoor-rig-dark (down period)")
    out["readings"].append(row)
    print("dark", {k: row.get(k) for k in ("kind", "reason")}, flush=True)
    # the first window again: refused, because it already has its official reading
    first = out["readings"][0]
    before = int(read(addr, "get_counts")["readings"])
    rr = write(addr, "read", [first["meter_id"], first["window_start"], 5])
    time.sleep(20)
    rr["readings_after"] = int(read(addr, "get_counts")["readings"])
    rr["readings_before"] = before
    rr["window_readings"] = read(addr, "get_window_readings", [first["meter_id"], first["window_start"], 5])
    out["reread"] = rr
    print("reread", rr, flush=True)
    OUT.write_text(json.dumps(out, indent=2, default=str) + "\n")
    # the consumer pins a window that has not started yet, then settles from its official reading
    cdep = deploy(BUILD / "meter_consumer_example.py", [addr])
    caddr = cdep["address"]
    meter = out["meters"][0]["meter_id"]
    jstart = (int(time.time()) // 60 + 4) * 60
    job = write(caddr, "create_job", [meter, jstart, 5, TARGET])
    while time.time() < jstart + 6 * 60 + 5:
        time.sleep(5)
    jr = take(meter, jstart, "consumer window (rig-sixty)")
    settle = write(caddr, "settle_job", ["1"])
    j1 = None
    for _ in range(20):
        j1 = read(caddr, "get_job", ["1"])
        if j1.get("state") != "OPEN":
            break
        time.sleep(6)
    out["consumer"] = {"address": caddr, "deploy": cdep, "create": job, "window_start": jstart, "reading": jr, "settle": settle, "job_1": j1,
                       "window_share": read(addr, "window_share_bp", [meter, jstart, 5, TARGET])}
    out["counts"] = read(addr, "get_counts")
    OUT.write_text(json.dumps(out, indent=2, default=str) + "\n")
    print("done", out["counts"], j1, flush=True)


if __name__ == "__main__":
    main()
