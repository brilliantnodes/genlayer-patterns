#!/usr/bin/env python3
"""Mutation check: break the contract on purpose, one change at a time, and
confirm that the direct-mode tests catch every break.

    cd meter-reader && PYTHONPATH=. ../venv/bin/python tools/mutate.py

Each mutant is written to a temporary file and the tests are pointed at it
with MR_CONTRACT; contracts/meter_reader.py itself is never modified.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / "contracts" / "meter_reader.py").read_text()

MUTANTS = [
    # rules and limits
    ("default tolerance 1% -> 10%", "DEFAULT_TOLERANCE_BP = 100", "DEFAULT_TOLERANCE_BP = 1000"),
    ("tolerance cap 5% -> 50%", "MAX_TOLERANCE_BP = 500", "MAX_TOLERANCE_BP = 5000"),
    ("no coverage rule when reading", "if len(seen) * BP < MIN_COVERAGE_BP * slots:", "if False:"),
    ("no coverage rule on the leader's result", 'if len(out) * BP < MIN_COVERAGE_BP * slots:\n        raise ValueError("coverage below the minimum")', 'if False:\n        raise ValueError("coverage below the minimum")'),
    ("2-minute slots allowed", "SLOT_CHOICES = (1, 5, 10, 15, 30, 60)", "SLOT_CHOICES = (1, 2, 5, 10, 15, 30, 60)"),
    ("read before the window is over", 'opens = end + slot + spec["publish_lag_minutes"] * 60', 'opens = end + spec["publish_lag_minutes"] * 60'),
    ("window start off the minute", "if start <= 0 or start % 60 != 0:", "if start <= 0:"),
    ("more than 96 slots", "if slots < MIN_SLOTS or slots > MAX_SLOTS:", "if slots < MIN_SLOTS:"),
    ("per-meter list unbounded", "json.dumps(ids[-MAX_PER_METER:])", "json.dumps(ids)"),
    ("publishing lag ignored", 'opens = end + slot + spec["publish_lag_minutes"] * 60', "opens = end + slot"),
    ("publishing lag uncapped", "if publish_lag_minutes < 0 or publish_lag_minutes > MAX_PUBLISH_LAG_MINUTES:", "if publish_lag_minutes < 0:"),
    ("window index keeps every id", 'if len(w["first"]) < MAX_FIRST_PER_WINDOW:', "if True:"),
    ("window index loses the latest", 'w["latest"] = new_id', 'w["latest"] = w["first"][0]'),
    ("window index not counted", 'w["count"] += 1', "pass"),
    # interpreting the copy
    ("another site accepted", 'if kind not in ("series_stats", "series_not_found") or spec["source_name"].lower() not in on_page:', 'if kind not in ("series_stats", "series_not_found"):'),
    ("unavailable page read as stats", 'if kind not in ("series_stats", "series_not_found")', 'if kind not in ("series_stats", "series_not_found", "unavailable")'),
    ("non-UTC page accepted", 'if not _yes(ans.get("times_utc")):\n        return {"kind": "NO_READING", "reason": "N2_FORMAT"}', 'if False:\n        return {"kind": "NO_READING", "reason": "N2_FORMAT"}'),
    ("misaligned rows accepted", "if (ts - start) % slot != 0:", "if False:"),
    ("conflicting rows accepted", "if idx in seen and seen[idx] != v:", "if False:"),
    ("unreadable row skipped", 'if v is None:\n            return {"kind": "NO_READING", "reason": "N2_FORMAT"}', "if v is None:\n            continue"),
    ("rows after the window kept", "if ts is None or ts < start or ts >= end:", "if ts is None or ts < start:"),
    # units
    ("value and unit may disagree", "if given and _norm_unit(rest) and given != _norm_unit(rest):", "if False:"),
    ("count label ignored", 'if u != _norm_unit(spec["unit_label"]):\n            return None', "if False:\n            return None"),
    ("bare 0 refused", 'if v == 0 and u == "":\n        return 0', 'if False:\n        return 0'),
    ("negative values read", "if v is None or v != v or v < 0 or v > 1e24:", "if v is None or v != v or v > 1e24:"),
    ("decimal comma read as thousands", 'if not (groups[0].isdigit() and 1 <= len(groups[0]) <= 3 and all(g.isdigit() and len(g) == 3 for g in groups[1:])):\n            return None', "if False:\n            return None"),
    ("count scale lost", "out = int(round(v * COUNT_SCALE))", "out = int(round(v))"),
    ("hashrate unit label accepted", 'if unit_family == "hashrate" and unit_label != "":', "if False:"),
    # leader result checks
    ("leader rows beyond the window", "if i <= last or i < 0 or i >= slots or v < 0 or v > MAX_VALUE:", "if i <= last or i < 0 or v < 0 or v > MAX_VALUE:"),
    ("leader rows out of order", "if i <= last or i < 0 or i >= slots", "if i < 0 or i >= slots"),
    ("leader negative value", "or v < 0 or v > MAX_VALUE:\n            raise ValueError(\"bad row values\")", "or v > MAX_VALUE:\n            raise ValueError(\"bad row values\")"),
    ("not listed with rows", 'if out:\n            raise ValueError("not listed with rows")', 'if False:\n            raise ValueError("not listed with rows")'),
    ("unknown reason accepted", 'if r.get("reason") not in NO_READING_REASONS:', "if False:"),
    ("leader error accepted", "if not isinstance(leader_result, gl.vm.Return):\n                return False\n            try:\n                leader = _check_outcome", "if not isinstance(leader_result, gl.vm.Return):\n                return True\n            try:\n                leader = _check_outcome"),
    # agreement
    ("kind not compared", 'if a["kind"] != b["kind"]:\n        return False\n    if a["kind"] == "NO_READING":\n        return a["reason"] == b["reason"]', 'if a["kind"] == "NO_READING" and b["kind"] == "NO_READING":\n        return a["reason"] == b["reason"]'),
    ("reason not compared", 'return a["reason"] == b["reason"]', "return True"),
    ("slot set not compared", 'if [i for i, _ in a["rows"]] != [i for i, _ in b["rows"]]:\n        return False', 'if False:\n        return False'),
    ("tolerance ten times looser", "return abs(a - b) * BP <= tol_bp * max(a, b)", "return abs(a - b) * BP <= 10 * tol_bp * max(a, b)"),
    ("values not compared", "return all(_close(x[1], y[1], tol) for x, y in zip(a[\"rows\"], b[\"rows\"]))", "return True"),
    # consumer figures
    ("share ignores missing slots", "return {\"share_bp\": (BP * got) // (target * slots), \"rule\": \"S1_CAPPED_PRO_RATA\"}", "return {\"share_bp\": (BP * got) // (target * len(outcome[\"rows\"])), \"rule\": \"S1_CAPPED_PRO_RATA\"}"),
    ("share not capped", "got = sum(min(v, target) for _, v in outcome[\"rows\"])", "got = sum(v for _, v in outcome[\"rows\"])"),
    ("not listed pays", '{"share_bp": 0, "rule": "Z1_NOT_LISTED"}', '{"share_bp": BP, "rule": "Z1_NOT_LISTED"}'),
    ("mean over listed slots only", '"mean_all_slots": str(total // slots)', '"mean_all_slots": str(total // len(values))'),
    ("share on a no-reading", 'if outcome["kind"] == "NO_READING":\n            raise gl.vm.UserError("this reading has no numbers: " + outcome["reason"])', 'if False:\n            raise gl.vm.UserError("this reading has no numbers: " + outcome["reason"])'),
    # URL filter and inputs
    ("backslash allowed", 'if "\\\\" in url:', "if False:"),
    ("user info allowed", 'if "@" in authority:', "if False:"),
    ("metadata range allowed", "or (a == 169 and b == 254)", ""),
    ("octal and padded labels allowed", "lab.isdigit() and str(int(lab)) == lab and int(lab) <= 255", "lab.isdigit() and int(lab) <= 255"),
    ("internal suffixes allowed", 'PRIVATE_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home", ".arpa", ".corp", ".intranet")', 'PRIVATE_SUFFIXES = (".localhost",)'),
    ("single-label hosts allowed", "if len(labels) < 2 or any(lab == \"\" for lab in labels):", "if any(lab == \"\" for lab in labels):"),
    ("short source name allowed", "if len(source_name) < 3:", "if False:"),
    ("page not cut", "return text[:PAGE_CHARS]", "return text"),
    ("markers not removed", 'text = text.replace(PAGE_BEGIN, " ").replace(PAGE_END, " ").replace("=====", " ")', "text = text"),
]


def main() -> int:
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    caught = 0
    tmp = Path(tempfile.mkdtemp(prefix="mr-mutants-"))
    for i, (name, old, new) in enumerate(MUTANTS, 1):
        n = SRC.count(old)
        if n != 1:
            print(f"SETUP ERROR  {name}: pattern found {n} times")
            return 2
        path = tmp / f"mutant_{i:02d}.py"
        path.write_text(SRC.replace(old, new))
        r = subprocess.run([sys.executable, "-m", "pytest", "tests/direct", "-q", "-x", "-p", "no:cacheprovider"],
                           cwd=ROOT, env={**env, "MR_CONTRACT": str(path)}, capture_output=True, text=True)
        ok = r.returncode != 0
        caught += ok
        print(f"{'caught ' if ok else 'MISSED '} {i:2d} {name}", flush=True)
    print(f"\n{caught} of {len(MUTANTS)} mutants caught")
    return 0 if caught == len(MUTANTS) else 1


if __name__ == "__main__":
    sys.exit(main())
