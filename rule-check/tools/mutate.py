#!/usr/bin/env python3
"""Mutation check: break the contract on purpose, one change at a time, and
confirm that the direct-mode tests catch every break.

    cd rule-check && PYTHONPATH=. ../venv/bin/python tools/mutate.py

Each mutant is written to a temporary file and the tests are pointed at it
with RC_CONTRACT; contracts/rule_check.py itself is never modified.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / "contracts" / "rule_check.py").read_text()

MUTANTS = [
    # the rule table
    ("last matching rule wins", 'for r in tpl["rules"]:\n        if all(', 'for r in reversed(tpl["rules"]):\n        if all('),
    ("any condition is enough", "if all(answers.get(k) in allowed for k, allowed in r[\"when\"].items()):", "if any(answers.get(k) in allowed for k, allowed in r[\"when\"].items()):"),
    ("default rule id renamed", 'DEFAULT_RULE = "DEFAULT"', 'DEFAULT_RULE = "NONE"'),
    # answers
    ("invalid answer kept", "if a not in f[\"options\"]:\n            a = UNCLEAR\n        if f[\"page\"]", "if False:\n            a = UNCLEAR\n        if f[\"page\"]"),
    ("answers case-sensitive", 'a = str(got.get(f["key"], "")).strip().lower()', 'a = str(got.get(f["key"], "")).strip()'),
    ("unread page not forced unclear", 'if f["page"] != "" and not pages_read[tpl["pages"].index(f["page"])]:\n            a = UNCLEAR', 'if False:\n            a = UNCLEAR'),
    ("notes not capped", "for n in notes_in[:MAX_NOTES]:", "for n in notes_in:"),
    ("notes not cut", "text = \" \".join(str(n).split())[:MAX_NOTE_LEN]", "text = \" \".join(str(n).split())"),
    ("unclear not added", 'facts.append({"key": key, "question": question, "options": opts + [UNCLEAR], "page": page})', 'facts.append({"key": key, "question": question, "options": opts, "page": page})'),
    # leader result checks
    ("leader verdict not re-derived", 'if (verdict, rule) != (r.get("verdict"), r.get("rule")):\n        raise ValueError("the answers do not give this verdict")', 'if False:\n        raise ValueError("the answers do not give this verdict")'),
    ("leader answer from an unread page", 'if f["page"] != "" and not pr[tpl["pages"].index(f["page"])] and a != UNCLEAR:', "if False:"),
    ("leader answers need not cover every fact", 'if not isinstance(answers, dict) or set(answers) != {f["key"] for f in tpl["facts"]}:', "if not isinstance(answers, dict):"),
    ("leader answer outside the options", 'if a not in f["options"]:\n            raise ValueError("answer not among the options")', 'if False:\n            raise ValueError("answer not among the options")'),
    ("leader pages_read length unchecked", 'if not isinstance(pr, list) or len(pr) != len(tpl["pages"]) or not all(isinstance(x, bool) for x in pr):', "if not isinstance(pr, list):"),
    ("unreadable with a readable page", 'if any(pr) or r.get("rule") != UNREADABLE:', "if False:"),
    ("verdict with no readable page", 'if not any(pr):\n        raise ValueError("a verdict needs a readable page")', 'if False:\n        raise ValueError("a verdict needs a readable page")'),
    ("leader notes unchecked", 'if not isinstance(notes, list) or len(notes) > MAX_NOTES or not all(isinstance(n, str) and len(n) <= MAX_NOTE_LEN for n in notes):', "if not isinstance(notes, list):"),
    ("leader error accepted", "if not isinstance(leader_result, gl.vm.Return):\n                return False", "if not isinstance(leader_result, gl.vm.Return):\n                return True"),
    # agreement
    ("rule not compared", 'if (leader["verdict"], leader["rule"]) != (mine["verdict"], mine["rule"]):', 'if leader["verdict"] != mine["verdict"]:'),
    # Not listed: comparing the rule id but not the verdict is an equivalent
    # mutant, because every rule id (and DEFAULT) fixes its verdict.
    ("deciding facts not compared", 'return all(leader["answers"][k] == mine["answers"][k] for k in _used_facts(tpl, leader["rule"]))', "return True"),
    ("every fact compared", 'for k in _used_facts(tpl, leader["rule"]))', 'for k in leader["answers"])'),
    ("unreadable agrees with anything", 'return leader["verdict"] == mine["verdict"]\n    if (leader', 'return True\n    if (leader'),
    ("unreadable stored", 'if res["verdict"] == UNREADABLE:\n            raise gl.vm.UserError("none of the pages could be read")', 'if False:\n            raise gl.vm.UserError("none of the pages could be read")'),
    ("unreadable when one page is unread", "if not any(pages_read):\n        # Returned", "if not all(pages_read):\n        # Returned"),
    # template validation
    ("rule id DEFAULT allowed", "and set(s) <= RULE_ID_CHARS and s != DEFAULT_RULE", "and set(s) <= RULE_ID_CHARS"),
    ("duplicate fact keys allowed", "if not _is_slug(key) or key in keys:", "if not _is_slug(key):"),
    ("duplicate rule ids allowed", "if not _is_rule_id(rid) or rid in ids:", "if not _is_rule_id(rid):"),
    ("fact page need not exist", 'if page != "" and page not in pages:', "if False:"),
    ("unclear allowed as a listed option", "if not _is_slug(o) or o == UNCLEAR or o in opts:", "if not _is_slug(o) or o in opts:"),
    ("condition answer need not exist", 'if a not in by_key[k]["options"]:\n                    raise', 'if False:\n                    raise'),
    ("empty rule allowed", 'if not isinstance(when_in, dict) or not 1 <= len(when_in) <= MAX_CONDITIONS:', "if not isinstance(when_in, dict):"),
    ("too many facts", 'if not isinstance(facts_in, list) or not 1 <= len(facts_in) <= MAX_FACTS:', "if not isinstance(facts_in, list) or not facts_in:"),
    ("too many pages", 'if not isinstance(pages_in, list) or not 1 <= len(pages_in) <= MAX_PAGES:', "if not isinstance(pages_in, list) or not pages_in:"),
    ("huge template JSON", 'if not isinstance(s, str) or len(s) > MAX_TEMPLATE_JSON:', "if not isinstance(s, str):"),
    ("default verdict unchecked", 'if not _is_slug(default_verdict):\n        raise', 'if False:\n        raise'),
    # checks
    ("url count unchecked", 'if not isinstance(url_list, list) or len(url_list) != len(tpl["pages"]) or not all(isinstance(u, str) for u in url_list):', "if not isinstance(url_list, list):"),
    ("long subject allowed", "if len(subject) > MAX_SUBJECT_LEN:", "if False:"),
    ("per-template list unbounded", "json.dumps(ids[-MAX_PER_TEMPLATE:])", "json.dumps(ids)"),
    # URL filter and prompt
    ("backslash allowed", 'if "\\\\" in url:', "if False:"),
    ("user info allowed", 'if "@" in authority:', "if False:"),
    ("metadata range allowed", "or (a == 169 and b == 254)", ""),
    ("hex host allowed", "if len(labels) != 4 or not all(lab.isdigit() and str(int(lab)) == lab and int(lab) <= 255 for lab in labels):\n            return True", "if len(labels) != 4:\n            return True"),
    ("markers not removed", 'text = str(text or "").replace("=====", " ")', 'text = str(text or "")'),
    ("page not cut", "return text[:PAGE_CHARS]", "return text"),
    ("page tie not in the prompt", 'where = f" Answer from the {f[\'page\'].upper()} page only." if f["page"] else ""', 'where = ""'),
]


def main() -> int:
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    caught = 0
    tmp = Path(tempfile.mkdtemp(prefix="rc-mutants-"))
    for i, (name, old, new) in enumerate(MUTANTS, 1):
        n = SRC.count(old)
        if n != 1:
            print(f"SETUP ERROR  {name}: pattern found {n} times")
            return 2
        path = tmp / f"mutant_{i:02d}.py"
        path.write_text(SRC.replace(old, new))
        r = subprocess.run([sys.executable, "-m", "pytest", "tests/direct", "-q", "-x", "-p", "no:cacheprovider"],
                           cwd=ROOT, env={**env, "RC_CONTRACT": str(path)}, capture_output=True, text=True)
        ok = r.returncode != 0
        caught += ok
        print(f"{'caught ' if ok else 'MISSED '} {i:2d} {name}", flush=True)
    print(f"\n{caught} of {len(MUTANTS)} mutants caught")
    return 0 if caught == len(MUTANTS) else 1


if __name__ == "__main__":
    sys.exit(main())
