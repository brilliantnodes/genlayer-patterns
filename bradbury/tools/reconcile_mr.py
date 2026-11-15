import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from live_mr import read, TARGET
p = Path(__file__).resolve().parent.parent / "results" / "meter-reader.json"
out = json.loads(p.read_text()); A = out["address"]
by_meter = {}
for m in out["meters"]:
    by_meter[m["meter_id"]] = sorted(read(A, "get_readings", [m["meter_id"], 10]), key=lambda r: int(r["id"]))
used = {}
for row in out["readings"]:
    lst = by_meter[row["meter_id"]]
    k = used.get(row["meter_id"], 0); used[row["meter_id"]] = k + 1
    r = lst[k]
    row.update({"reading_id": r["id"], "kind": r.get("kind"), "reason": r.get("reason"), "values": [x.get("value") for x in r.get("table", [])]})
    row.pop("share_bp", None)
    if r.get("kind") != "NO_READING":
        row["share_bp"] = read(A, "delivery_share_bp", [r["id"], TARGET]).get("share_bp")
    print(row["example"], row["reading_id"], row["kind"], row.get("reason"), row.get("share_bp"), row["values"])
out["note"] = "reading ids and values rebuilt from get_readings on chain (a lagging get_counts read right after a write had recorded the wrong id for the gappy row)"
out["counts"] = read(A, "get_counts")
p.write_text(json.dumps(out, indent=2, default=str) + "\n")
