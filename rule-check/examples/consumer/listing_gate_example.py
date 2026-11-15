# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""
ListingGateExample: a small consumer of RuleCheck.

A fictional listing desk ("Saltmarsh Exchange", which does not exist) lists a
coin only when a RuleCheck check says its "no premine" claim is supported. The
gate reads the stored check through gl.get_contract_at(...).view(). It reads
no web page and calls no model.

What the gate checks before it uses a check:

- the check was made with the one template the gate trusts (pinned at deploy).
  Anyone can create RuleCheck templates, so a gate that only looked at the
  verdict would accept "supported" from a template whose rules say anything.
- the check is recent enough (max_age_hours, 0 = no limit), so an old check
  of a page that has since changed cannot be replayed;
- the check's subject is the one the caller names, when the caller names one;
- the check has not been used before. One check gives one decision.

Verdicts the gate admits on, and refuses on, are fixed at deploy. Any other
verdict (the template's default, such as "undetermined") gives RECHECK: the
decision is recorded but nothing is decided, and a new check may be run.

A real consumer would list the coin, release a payment or open a dispute at
the point where this example records ADMIT or REFUSE. Test GEN on Studio only.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from genlayer import *

ADMIT = "ADMIT"
REFUSE = "REFUSE"
RECHECK = "RECHECK"
MAX_VERDICTS = 8
MAX_AGE_HOURS = 24 * 30


def _slug_list(text: str, what: str) -> list:
    try:
        v = json.loads(text)
    except Exception:
        raise ValueError(f"{what} must be a JSON list of verdicts")
    if not isinstance(v, list) or not v or len(v) > MAX_VERDICTS:
        raise ValueError(f"{what} must list 1 to {MAX_VERDICTS} verdicts")
    out = []
    for x in v:
        if not isinstance(x, str) or not x or len(x) > 32 or not all(ch.islower() or ch.isdigit() or ch == "_" for ch in x) or not x[0].isalpha():
            raise ValueError(f"{what}: each verdict must be a lowercase slug")
        if x in out:
            raise ValueError(f"{what}: duplicate verdict {x}")
        out.append(x)
    return out


def _parse_config(template_id: str, admit_verdicts: str, refuse_verdicts: str, max_age_hours: int) -> dict:
    tid = str(template_id).strip()
    if not tid.isdigit() or tid.startswith("0"):
        raise ValueError("template_id must be a RuleCheck template id such as 1")
    admit = _slug_list(admit_verdicts, "admit_verdicts")
    refuse = _slug_list(refuse_verdicts, "refuse_verdicts")
    both = sorted(set(admit) & set(refuse))
    if both:
        raise ValueError("a verdict cannot both admit and refuse: " + ", ".join(both))
    age = int(max_age_hours)
    if age < 0 or age > MAX_AGE_HOURS:
        raise ValueError(f"max_age_hours must be 0 (no limit) to {MAX_AGE_HOURS}")
    return {"template_id": tid, "admit": admit, "refuse": refuse, "max_age_hours": age}


def _ts(text) -> float:
    """RuleCheck stores checked_at as an ISO time ending in Z."""
    s = str(text).strip().replace(" ", "T")
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    d = datetime.fromisoformat(s)
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.timestamp()


def _decide(cfg: dict, check: dict, now, expected_subject: str = "") -> dict:
    """Pure decision from one stored RuleCheck check. Raises ValueError when
    the check must not be used at all."""
    if str(check.get("template_id")) != cfg["template_id"]:
        raise ValueError(f"check {check.get('id')} was made with template {check.get('template_id')}; this gate accepts only template {cfg['template_id']}")
    want = " ".join(str(expected_subject).split())
    if want and want != str(check.get("subject", "")):
        raise ValueError(f"check {check.get('id')} is about \"{check.get('subject', '')}\", not \"{want}\"")
    try:
        age_s = _ts(now) - _ts(check["checked_at"])
    except Exception:
        raise ValueError(f"check {check.get('id')} has no readable check time")
    if age_s < -300:
        raise ValueError("check time is in the future")
    if cfg["max_age_hours"] and age_s > cfg["max_age_hours"] * 3600:
        raise ValueError(f"check {check.get('id')} is {int(age_s // 3600)} h old; this gate accepts checks up to {cfg['max_age_hours']} h old")
    verdict = str(check.get("verdict"))
    decision = ADMIT if verdict in cfg["admit"] else REFUSE if verdict in cfg["refuse"] else RECHECK
    return {
        "decision": decision,
        "verdict": verdict,
        "rule": str(check.get("rule")),
        "deciding_facts": dict(check.get("deciding_facts") or {}),
        "subject": str(check.get("subject", "")),
        "checked_at": str(check["checked_at"]),
    }


@allow_storage
@dataclass
class Decision:
    id: str
    check_id: str
    decided_by: str
    decided_at: str
    result_json: str


class ListingGateExample(gl.Contract):
    rule_check: Address
    config_json: str
    decisions: TreeMap[str, Decision]
    used_checks: TreeMap[str, str]  # check id -> decision id
    latest_by_subject: TreeMap[str, str]  # subject -> decision id
    count: u256

    def __init__(self, rule_check_address: str, template_id: str, admit_verdicts: str, refuse_verdicts: str, max_age_hours: int = 24):
        try:
            cfg = _parse_config(template_id, admit_verdicts, refuse_verdicts, max_age_hours)
        except ValueError as e:
            raise gl.vm.UserError(str(e))
        self.rule_check = Address(rule_check_address)
        self.config_json = json.dumps(cfg, sort_keys=True)
        self.count = u256(0)

    @gl.public.write
    def decide(self, check_id: str, expected_subject: str = "") -> dict:
        """Read one RuleCheck check and record the gate's decision."""
        check_id = str(check_id).strip()
        if check_id in self.used_checks:
            raise gl.vm.UserError(f"check {check_id} was already used for decision {self.used_checks[check_id]}")
        check = gl.get_contract_at(self.rule_check).view().get_check(check_id)
        try:
            res = _decide(json.loads(self.config_json), check, gl.message_raw["datetime"], expected_subject)
        except ValueError as e:
            raise gl.vm.UserError(str(e))
        new_id = str(int(self.count) + 1)
        d = Decision(id=new_id, check_id=check_id, decided_by=gl.message.sender_address.as_hex, decided_at=str(gl.message_raw["datetime"]), result_json=json.dumps(res, sort_keys=True))
        self.decisions[new_id] = d
        self.used_checks[check_id] = new_id
        self.latest_by_subject[res["subject"]] = new_id
        self.count = u256(int(self.count) + 1)
        return self._view(d)

    def _view(self, d: Decision) -> dict:
        return {"id": d.id, "check_id": d.check_id, "decided_by": d.decided_by, "decided_at": d.decided_at, **json.loads(d.result_json)}

    @gl.public.view
    def get_decision(self, decision_id: str) -> dict:
        if decision_id not in self.decisions:
            raise gl.vm.UserError("no such decision")
        return self._view(self.decisions[decision_id])

    @gl.public.view
    def get_latest_for_subject(self, subject: str) -> dict:
        s = " ".join(str(subject).split())
        if s not in self.latest_by_subject:
            raise gl.vm.UserError("no decision for this subject")
        return self._view(self.decisions[self.latest_by_subject[s]])

    @gl.public.view
    def get_config(self) -> dict:
        return {"rule_check": self.rule_check.as_hex, **json.loads(self.config_json)}

    @gl.public.view
    def get_count(self) -> int:
        return int(self.count)
