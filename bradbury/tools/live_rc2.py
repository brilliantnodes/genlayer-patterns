"""Follow-up on Bradbury: retry the Saltmarsh status check (template 2), then
give it to the gate to show the template guard. Waits until the contract's
count advances before reading any id (Bradbury reads can lag a write)."""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from live_mr import write, read

RC = "0x7525aC6d34dd2189E290C4396d9b78f7eD1196b4"
OUT = Path(__file__).resolve().parent.parent / "results" / "rule-check.json"
EX = Path(__file__).resolve().parents[2] / "rule-check" / "examples"

def wait_count(addr, fn, key, want, minutes=5):
    end = time.time() + minutes * 60
    while time.time() < end:
        v = read(addr, fn)
        v = v[key] if key else v
        if int(v) >= want:
            return int(v)
        time.sleep(6)
    return int(v)

out = json.loads(OUT.read_text())
gate = out["gate"]["address"]
spec = json.loads((EX / "check-saltmarsh-status.json").read_text())
attempts = []
cid = None
for i in range(3):
    before = int(read(RC, "get_counts")["checks"])
    row = write(RC, "check", ["2", json.dumps(spec["urls"]), spec.get("subject", "")])
    attempts.append(row)
    after = wait_count(RC, "get_counts", "checks", before + 1, minutes=2)
    if after > before:
        cid = str(after)
        break
out["saltmarsh_attempts"] = attempts
if cid:
    c = read(RC, "get_check", [cid])
    out["checks"] = [x for x in out["checks"] if x["example"] != "check-saltmarsh-status"]
    out["checks"].append({**attempts[-1], "example": "check-saltmarsh-status", "template_id": "2", "check_id": cid, "verdict": c.get("verdict"),
                          "rule": c.get("rule"), "deciding_facts": c.get("deciding_facts"), "subject": c.get("subject")})
    print("saltmarsh", cid, c.get("verdict"), c.get("rule"), flush=True)
    g0 = int(read(gate, "get_count"))
    row = write(gate, "decide", [cid, ""])
    time.sleep(10)
    g1 = int(read(gate, "get_count"))
    out["refused"] = [r for r in out["refused"] if not r["case"].startswith("check from template 2")]
    out["refused"].insert(0, {**row, "case": "check from template 2 (pool status)", "check_id": cid, "gate_count_before": g0, "gate_count_after": g1})
    out["refused"][1]["note"] = "the first run's template-2 attempt used check 3 by mistake (a lagging count); check 3 was already used, so it is shown here as the reused-check case"
    print("refused template-2", row["execution"], g0, g1, flush=True)
out["counts"] = read(RC, "get_counts"); out["gate_count"] = read(gate, "get_count")
OUT.write_text(json.dumps(out, indent=2, default=str) + "\n")
print("done", out["counts"], out["gate_count"], flush=True)
