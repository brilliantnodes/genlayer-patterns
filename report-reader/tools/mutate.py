#!/usr/bin/env python3
"""Mutation check: break each contract on purpose, one change at a time, and
confirm that the direct-mode tests catch every break.

    cd report-reader && PYTHONPATH=. ../venv/bin/python tools/mutate.py [reader|earnout]

Each mutant is written to a temporary file and the tests are pointed at it
with RR_CONTRACT or EO_CONTRACT; the contracts themselves are never modified.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

READER = [
    # one official reading, windows and the clock
    ("official reading can be replaced", 'if p["official"] is not None:\n            raise gl.vm.UserError(f"period {n} already has', 'if False:\n            raise gl.vm.UserError(f"period {n} already has'),
    ("any outcome becomes official", 'if outcome["kind"] == "READ":\n            p["official"]', 'if True:\n            p["official"]'),
    ("not-published becomes official", 'if outcome["kind"] == "READ":\n            p["official"]', 'if outcome["kind"] in ("READ", "NOT_PUBLISHED"):\n            p["official"]'),
    ("read before the window opens", "if now < _opens(spec, n):\n            raise", "if now < _ends(spec)[n]:\n            raise"),
    ("read after the window closes", "if now >= _closes(spec, n):\n            return", "if False:\n            return"),
    ("clock runs backwards", "now = max(int(self.clocks[report_id]), self._tx_time())", "now = self._tx_time()"),
    ("publishing lag ignored", 'return _ends(spec)[n] + spec["publish_lag_minutes"] * 60', "return _ends(spec)[n]"),
    ("MISSING before the close is settled", 'return "MISSING" if clock >= _closes(spec, n) else "CLOSING"', 'return "MISSING"'),
    ("READ shown before it happened", 'if off is not None and off["at"] <= at:', "if off is not None:"),
    ("no WAITING status", 'if at < _opens(spec, n):\n        return "WAITING"', 'if False:\n        return "WAITING"'),
    ("tick lists periods that were read", 'if now >= _closes(spec, n) and self._period(report_id, n)["official"] is None]', "if now >= _closes(spec, n)]"),
    ("each period reads page 0", 'return spec["url_template"].replace("{n}", str(n))', 'return spec["url_template"].replace("{n}", "0")'),
    ("attempts unbounded", 'if len(p["attempts"]) < MAX_ATTEMPTS_KEPT:', "if True:"),
    ("attempts not counted", 'p["attempt_count"] += 1', "pass"),
    # the specification
    ("window may be one minute", "MIN_WINDOW_MINUTES = 30  #", "MIN_WINDOW_MINUTES = 1  #"),
    ("nine figures", "MAX_FIGURES = 8", "MAX_FIGURES = 9"),
    ("25 periods", "MAX_PERIODS = 24", "MAX_PERIODS = 25"),
    ("period ends may repeat", "if ends and ts <= ends[-1]:", "if ends and ts < ends[-1]:"),
    ("no five-year limit", "if ends[-1] > now + MAX_AHEAD_SECONDS:", "if False:"),
    ("unknown field allowed", "extra = [k for k in spec.keys() if k not in SPEC_KEYS]", "extra = []"),
    ("unknown figure field allowed", "extra = [k for k in f.keys() if k not in FIGURE_KEYS]", "extra = []"),
    ("duplicate figure keys", "if key in seen:", "if False:"),
    ("step need not be a power of ten", ' or s.rstrip("0") != "1"', ""),
    ("{n} twice", 'if tpl.count("{n}") != 1 or', 'if tpl.count("{n}") < 1 or'),
    ("{n} in the host", 'if "/" not in after_scheme or after_scheme.index("{n}") < after_scheme.index("/"):', "if False:"),
    ("query allowed", 'if "?" in tpl or "#" in tpl:', 'if "#" in tpl:'),
    ("private hosts allowed", "if _is_private_host(_host_of(url)):", "if False:"),
    ("labels not normalised", "nl = _norm_label(lab)", "nl = lab"),
    ("trailing colon kept", 'while s.endswith(":"):', "while False:"),
    ("digest over the raw input", "digest=_digest(spec)", 'digest=_digest({"raw": spec_json})'),
    # interpreting the copy
    ("issuer not whole words", 'f" {name} " not in f" {on_page} "', "name not in on_page"),
    ("issuer not checked", 'kind not in ("periodic_report", "not_published") or f" {name} " not in f" {on_page} ":', 'kind not in ("periodic_report", "not_published"):'),
    ("draft accepted", 'if _yes(ans.get("marked_draft")):', "if False:"),
    ("period not checked", 'if not _period_matches(ans.get("period_end_on_page"), _ends(spec)[n]):', "if False:"),
    ("currency not checked", 'if not _currency_matches(ans.get("currency_on_page"), spec["currency"]):', "if False:"),
    ("decimal comma mark accepted", 'not in (".", "none"):', 'not in (".", "none", ","):'),
    ("decimal-comma page accepted", 'if _decimal_comma_page(page):\n        return {"kind": "NO_READING", "reason": "N2_FORMAT"}', 'if False:\n        return {"kind": "NO_READING", "reason": "N2_FORMAT"}'),
    ("conflict ignored", 'if _yes(f.get("conflicting")):', "if False:"),
    ("LTM ignored", 'if fs["ltm"] and not _yes(f.get("ltm_labelled")):', "if False:"),
    ("closed label list ignored", 'if label_n not in fs["labels"]:', "if False:"),
    # anchored copying
    ("anchoring off", 'if not _anchored(page_n, label_n, f.get("value")):', "if False:"),
    ("anchor ten times further", "ANCHOR_CHARS = 160  #", "ANCHOR_CHARS = 1600  #"),
    ("number edges ignored", "if _number_edge_ok(page_n, lo + j, lo + j + len(value_n)):", "if True:"),
    ("leading digit ignored", 'if start > 0 and page[start - 1] in DIGITS + ".,":', "if False:"),
    ("trailing decimals ignored", 'if nxt in ".," and end + 1 < len(page) and page[end + 1] in DIGITS:', "if False:"),
    ("value without digits anchored", " or not any(c in DIGITS for c in value_n)", ""),
    ("scale words not checked", 'if mult is None or not _scale_ok(page_n, f.get("scale_text"), mult, spec["currency"]):', "if mult is None:"),
    ("scale words need not be printed", 'if st == "" or st not in page_n:', 'if st == "":'),
    ("units may name a scale", "return len(named) == 0", "return True"),
    ("scale words may name several scales", "return named == {mult}", "return mult in named"),
    ("'000 not read", "if \"'000\" in s or \"000s\" in s:\n        out.append(\"thousands\")", "if False:\n        out.append(\"thousands\")"),
    ("currency prefix kept", "if cur != low_code and cur.startswith(low_code):", "if False:"),
    # conversion and rounding
    ("magnitude keeps the sign", 'if fs["sign"] == "magnitude":\n            v = abs(v)', 'if fs["sign"] == "magnitude":\n            v = v'),
    ("finance-cost rule ignored", 'elif fs["sign"] == "finance_cost":', "elif False:"),
    ("always rounded down", 'q = _ceil_div(num, den) if rounding == "up" else num // den', "q = num // den"),
    ("rounded toward zero", 'q = _ceil_div(num, den) if rounding == "up" else num // den', "q = (abs(num) // den) * (1 if num >= 0 else -1)"),
    ("decimals ignored", "num, den = v * 10**decimals, d * step", "num, den = v, d * step"),
    ("JSON floats parsed", "out = json.loads(s, parse_float=str)", "out = json.loads(s)"),
    ("12.450 read as a number", 'if dot and "," not in s and len(frac) == 3', 'if False and dot and "," not in s and len(frac) == 3'),
    ("page not cut", "return text[:PAGE_CHARS]", "return text"),
    ("markers not removed", 'text = text.replace(PAGE_BEGIN, " ").replace(PAGE_END, " ").replace("=====", " ")', "text = text"),
    # leader result checks and agreement
    ("leader figure off the step", ' or v % int(fs["step"]) != 0:', ":"),
    ("leader figure keys not checked", "if not isinstance(figs, dict) or sorted(figs.keys()) != sorted(keys):", "if not isinstance(figs, dict):"),
    ("leader negative magnitude", 'if fs["sign"] == "magnitude" and v < 0:\n            raise', "if False:\n            raise"),
    ("unknown reason accepted", 'if r.get("reason") not in NO_READING_REASONS:', "if False:"),
    ("leader error accepted", "if not isinstance(leader_result, gl.vm.Return):\n                return False", "if not isinstance(leader_result, gl.vm.Return):\n                return True"),
    ("figures not compared", 'return a["figures"] == b["figures"]', "return True"),
    ("reason not compared", 'return a.get("reason", "") == b.get("reason", "")', "return True"),
    ("kind not compared", 'if a["kind"] != b["kind"]:\n        return False', 'if False:\n        return False'),
]

EARNOUT = [
    ("nothing-below-floor rule off", "if value <= floor:\n        return 0", "if False:\n        return 0"),
    ("all-above-target rule off", "if value >= target:\n        return amount", "if False:\n        return amount"),
    ("share rounded up", "return amount * (value - floor) // (target - floor)", "return -(-amount * (value - floor) // (target - floor))"),
    ("missing pays the seller", 'return 0, deal["amount"], "report missing', 'return deal["amount"], 0, "report missing'),
    ("reader digest not checked", 'if reading.get("digest") != deal["digest"]:', "if False:"),
    ("pinned after the period ended", 'if reading.get("status") != "NOT_DUE":', 'if reading.get("status") not in ("NOT_DUE", "WAITING"):'),
    ("pinned digest not checked", 'if not isinstance(digest, str) or digest != report.get("digest"):', "if not isinstance(digest, str):"),
    ("figure not checked", "if figure not in figs:", "if False:"),
    ("period upper bound not checked", 'not 0 <= period < len(report["spec"]["period_ends"])', "not 0 <= period"),
    ("target may equal floor", "if target <= floor:", "if target < floor:"),
    ("leading zeros allowed", '(len(body) > 1 and body[0] == "0")', "False"),
    ("seller may be buyer", "if seller_hex.lower() == buyer.lower():", "if False:"),
    ("zero escrow accepted", "if value <= 0:\n            return self._refuse", "if value < 0:\n            return self._refuse"),
    ("refused value kept", "        self._credit(gl.message.sender_address.as_hex, value)\n        return {\"ok\": False", "        return {\"ok\": False"),
    ("withdraw above the credit", "if not 0 < amount <= have:", "if not 0 < amount:"),
    ("not-final status settles", 'if st != "READ":\n        if st == "CLOSING":', 'if st not in ("READ", "OPEN"):\n        if st == "CLOSING":'),
]

TARGETS = {
    "reader": ("contracts/report_reader.py", "RR_CONTRACT", READER, "tests/direct/test_report_reader.py"),
    "earnout": ("examples/consumer/earn_out_example.py", "EO_CONTRACT", EARNOUT, "tests/direct/test_earn_out.py"),
}


def run(name: str) -> tuple:
    rel, var, mutants, tests = TARGETS[name]
    src = (ROOT / rel).read_text()
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    tmp = Path(tempfile.mkdtemp(prefix=f"{name}-mutants-"))
    caught = 0
    for i, (label, old, new) in enumerate(mutants, 1):
        n = src.count(old)
        if n != 1:
            print(f"SETUP ERROR  {name} {label}: pattern found {n} times")
            sys.exit(2)
        path = tmp / f"mutant_{i:02d}.py"
        path.write_text(src.replace(old, new))
        r = subprocess.run([sys.executable, "-m", "pytest", tests, "-q", "-x", "-p", "no:cacheprovider"],
                           cwd=ROOT, env={**env, var: str(path)}, capture_output=True, text=True)
        ok = r.returncode != 0
        caught += ok
        print(f"{'caught ' if ok else 'MISSED '} {name} {i:2d} {label}", flush=True)
    return caught, len(mutants)


def main() -> int:
    names = sys.argv[1:] or list(TARGETS)
    total = got = 0
    for nm in names:
        c, n = run(nm)
        got, total = got + c, total + n
        print(f"{nm}: {c} of {n} mutants caught\n", flush=True)
    print(f"{got} of {total} mutants caught")
    return 0 if got == total else 1


if __name__ == "__main__":
    sys.exit(main())
