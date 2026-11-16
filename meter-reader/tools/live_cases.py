#!/usr/bin/env python3
"""Run the fictional live cases against MeterReader on GenLayer Studio and
write examples/live-runs.json.

    MR_KEY=<throwaway key> python tools/live_cases.py [--deploy]

With --deploy it deploys contracts/meter_reader.py first and writes
deployment.json. It then registers the five example meters, reads the last
five finished minutes of each, reads the rig-dark page again inside its down
period (6 to 9 minutes past every ten), computes delivery shares against
10 GH/s, tries to read the first window again (refused: it already has
its official reading), and deploys examples/consumer/meter_consumer_example.py,
which pins a meter, a window that has not started yet and a target, then
(after the window is read) settles from its official reading.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mr  # noqa: E402

ROOT = mr.ROOT
TARGET = str(10 * 10**9)  # 10 GH/s in H/s
EXAMPLES = ["fernhollow-rig-sixty", "fernhollow-rig-steady", "fernhollow-rig-gappy", "fernhollow-rig-ghost", "quillmoor-rig-dark"]


def agree(votes) -> int:
    return sum(1 for v in (votes or {}).values() if v == "agree")


def main():
    c, acct = mr.actor()
    if "--deploy" in sys.argv:
        dep = mr.deploy()
        (ROOT / "deployment.json").write_text(json.dumps(dep, indent=2) + "\n")
    addr = mr.deployed_address()
    out = {"address": addr, "meters": [], "readings": [], "consumer": {}}
    for name in EXAMPLES:
        spec = json.loads((ROOT / "examples" / f"{name}.json").read_text())
        tx, r = mr.write(c, addr, "register_meter", mr.register_args(spec), acct)
        out["meters"].append({"example": name, "meter_id": r["result"]["id"], "tx": tx})
        print("meter", r["result"]["id"], name, tx, flush=True)
    for m in out["meters"]:
        start = mr.last_window(1, 5)
        tx, r = mr.write(c, addr, "read", [m["meter_id"], start, 5], acct)
        res = r["result"]
        row = {"example": m["example"], "meter_id": m["meter_id"], "reading_id": res["id"], "window_start": res["window_start"], "kind": res["kind"], "reason": res["reason"],
               "values": [x["value"] for x in res["table"]], "agree": agree(r["votes"]), "tx": tx}
        if res["kind"] != "NO_READING":
            row["share_bp"] = mr.read_view(c, addr, "delivery_share_bp", [res["id"], TARGET])["share_bp"]
        out["readings"].append(row)
        print("reading", row, flush=True)
    # rig-dark again, inside its down period (minutes 6, 7 and 8 of every ten)
    dark = out["meters"][-1]["meter_id"]
    while True:
        t = time.gmtime()
        if t.tm_min % 10 == 6 and t.tm_sec < 30:
            break
        time.sleep(10)
    tx, r = mr.write(c, addr, "read", [dark, mr.last_window(1, 5), 5], acct)
    res = r["result"]
    out["readings"].append({"example": "quillmoor-rig-dark (down period)", "meter_id": dark, "reading_id": res["id"], "kind": res["kind"],
                            "reason": res["reason"], "values": [], "agree": agree(r["votes"]), "tx": tx})
    print("dark", out["readings"][-1], flush=True)
    # the first window again: it already has its official reading, so a second read is refused
    first = out["readings"][0]
    try:
        tx, r = mr.write(c, addr, "read", [first["meter_id"], first["window_start"], 5], acct)
        out["reread"] = {"tx": tx, "status": r.get("status"), "result": r.get("result")}
    except Exception as e:  # a refused write may surface as an error
        out["reread"] = {"error": str(e)[:300]}
    out["reread"]["window_readings"] = mr.read_view(c, addr, "get_window_readings", [first["meter_id"], first["window_start"], 5])
    print("reread", out["reread"], flush=True)
    # another contract pins a meter, a window and a target BEFORE the window, then settles from the official reading
    code = (ROOT / "examples" / "consumer" / "meter_consumer_example.py").read_text()
    dtx = c.deploy_contract(code=code, args=[addr])
    rc = mr.wait(c, dtx)
    caddr = rc.get("to_address") or rc.get("recipient")
    meter = out["meters"][0]["meter_id"]  # rig-sixty
    jstart = (int(time.time()) // 60 + 2) * 60  # a window that has not started yet
    jtx, rj = mr.write(c, caddr, "create_job", [meter, jstart, 5, TARGET], acct)
    opens = jstart + 6 * 60
    while time.time() < opens + 5:
        time.sleep(5)
    rtx, rr = mr.write(c, addr, "read", [meter, jstart, 5], acct)
    stx, rs_ = mr.write(c, caddr, "settle_job", ["1"], acct)
    out["consumer"] = {"address": caddr, "deploy_tx": dtx, "create_tx": jtx, "window_start": jstart, "read_tx": rtx, "reading": rr["result"],
                       "settle_tx": stx, "status": rs_["status"], "result": rs_["result"],
                       "window_share": mr.read_view(c, addr, "window_share_bp", [meter, jstart, 5, TARGET])}
    print("consumer", out["consumer"], flush=True)
    (ROOT / "examples" / "live-runs.json").write_text(json.dumps(out, indent=2) + "\n")


if __name__ == "__main__":
    main()
