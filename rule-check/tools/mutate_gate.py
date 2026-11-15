#!/usr/bin/env python3
"""Mutation check for the consumer example: break ListingGateExample on
purpose, one change at a time, and confirm the gate's tests catch every one.

    cd rule-check && PYTHONPATH=. ../venv/bin/python tools/mutate_gate.py

Each mutant goes to a temporary file and the tests are pointed at it with
LG_CONTRACT; examples/consumer/listing_gate_example.py is never modified.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / "examples" / "consumer" / "listing_gate_example.py").read_text()

MUTANTS = [
    # which checks may be used
    ("template not pinned", 'if str(check.get("template_id")) != cfg["template_id"]:', "if False:"),
    ("subject not compared", 'if want and want != str(check.get("subject", "")):', "if False:"),
    ("subject spaces not normalised", 'want = " ".join(str(expected_subject).split())', "want = str(expected_subject)"),
    ("no age limit", 'if cfg["max_age_hours"] and age_s > cfg["max_age_hours"] * 3600:', "if False:"),
    ("age limit off by one", "age_s > cfg[\"max_age_hours\"] * 3600", "age_s >= cfg[\"max_age_hours\"] * 3600 - 1"),
    ("future checks allowed", "if age_s < -300:", "if False:"),
    ("no skew tolerance", "if age_s < -300:", "if age_s < 0:"),
    ("bad time accepted", "        raise ValueError(f\"check {check.get('id')} has no readable check time\")", "        age_s = 0"),
    # the decision
    ("refuse list admits", "decision = ADMIT if verdict in cfg[\"admit\"] else REFUSE if verdict in cfg[\"refuse\"] else RECHECK",
     "decision = ADMIT if verdict in cfg[\"admit\"] + cfg[\"refuse\"] else RECHECK"),
    ("unknown verdict refuses", "else REFUSE if verdict in cfg[\"refuse\"] else RECHECK", "else REFUSE"),
    ("unknown verdict admits", "else REFUSE if verdict in cfg[\"refuse\"] else RECHECK", "else REFUSE if verdict in cfg[\"refuse\"] else ADMIT"),
    ("verdict trimmed", 'verdict = str(check.get("verdict"))', 'verdict = str(check.get("verdict")).strip().lower()'),
    # configuration
    ("overlap allowed", "if both:\n        raise", "if False:\n        raise"),
    ("duplicates allowed", "if x in out:\n            raise", "if False:\n            raise"),
    ("verdict not a slug", "if not isinstance(x, str) or not x or len(x) > 32 or not all(ch.islower() or ch.isdigit() or ch == \"_\" for ch in x) or not x[0].isalpha():",
     "if not isinstance(x, str):"),
    ("empty list allowed", "if not isinstance(v, list) or not v or len(v) > MAX_VERDICTS:", "if not isinstance(v, list):"),
    ("template id unchecked", 'if not tid.isdigit() or tid.startswith("0"):', "if False:"),
    ("negative age allowed", "if age < 0 or age > MAX_AGE_HOURS:", "if age > MAX_AGE_HOURS:"),
    ("huge age allowed", "if age < 0 or age > MAX_AGE_HOURS:", "if age < 0:"),
    ("age not stored", '"max_age_hours": age}', '"max_age_hours": 0}'),
]


def main() -> int:
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    caught = 0
    tmp = Path(tempfile.mkdtemp(prefix="lg-mutants-"))
    for i, (name, old, new) in enumerate(MUTANTS, 1):
        n = SRC.count(old)
        if n != 1:
            print(f"SETUP ERROR  {name}: pattern found {n} times")
            return 2
        path = tmp / f"mutant_{i:02d}.py"
        path.write_text(SRC.replace(old, new))
        r = subprocess.run([sys.executable, "-m", "pytest", "tests/direct/test_listing_gate.py", "-q", "-x", "-p", "no:cacheprovider"],
                           cwd=ROOT, env={**env, "LG_CONTRACT": str(path)}, capture_output=True, text=True)
        ok = r.returncode != 0
        caught += ok
        print(f"{'caught ' if ok else 'MISSED '} {i:2d} {name}", flush=True)
    print(f"\n{caught} of {len(MUTANTS)} mutants caught")
    return 0 if caught == len(MUTANTS) else 1


if __name__ == "__main__":
    sys.exit(main())
