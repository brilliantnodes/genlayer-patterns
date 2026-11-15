"""Direct-mode tests for ListingGateExample (examples/consumer).

The direct VM cannot run cross-contract calls, so decide() itself is proven
live on Studio (examples/consumer/live-runs.json). These tests cover the
constructor and the pure decision function _decide, which decide() calls on
the check it reads. Every coin, pool and exchange here is fictional.
"""

import json
import os
import sys

import pytest

GATE = os.environ.get("LG_CONTRACT", "examples/consumer/listing_gate_example.py")  # mutation runs point elsewhere
RC = "0x28BEC7C9A99cd19c101fbaB1CaFe0b6e4Db3f21e"
T0 = "2026-11-15T04:00:00.000000Z"


def check(**kw):
    c = {
        "id": "5",
        "template_id": "1",
        "subject": "Controlcoin (fictional): no premine",
        "checked_at": "2026-11-15T03:30:00.000000Z",
        "verdict": "supported",
        "rule": "R2_CLEAN_BLOCK1",
        "deciding_facts": {"block1_shown": "yes", "early_allocation": "no"},
    }
    c.update(kw)
    return c


@pytest.fixture
def gate(direct_vm, direct_deploy):
    direct_vm.warp(T0)
    return direct_deploy(GATE, RC, "1", '["supported"]', '["contradicted"]', 6)


@pytest.fixture
def mod(gate):
    for m in list(sys.modules.values()):
        if getattr(m, "ListingGateExample", None) is not None and hasattr(m, "_decide"):
            return m
    raise RuntimeError("contract module not found")


@pytest.fixture
def cfg(mod):
    return mod._parse_config("1", '["supported"]', '["contradicted"]', 6)


# ------------------------------------------------------------- constructor


def test_config_is_stored(gate):
    c = gate.get_config()
    assert c["template_id"] == "1"
    assert c["admit"] == ["supported"] and c["refuse"] == ["contradicted"]
    assert c["max_age_hours"] == 6
    assert c["rule_check"].lower() == RC.lower()
    assert gate.get_count() == 0


@pytest.mark.parametrize(
    "tid,admit,refuse,age,needle",
    [
        ("x", '["supported"]', '["contradicted"]', 6, "template_id"),
        ("01", '["supported"]', '["contradicted"]', 6, "template_id"),
        ("", '["supported"]', '["contradicted"]', 6, "template_id"),
        ("1", "supported", '["contradicted"]', 6, "JSON list"),
        ("1", "[]", '["contradicted"]', 6, "1 to 8"),
        ("1", '["Supported"]', '["contradicted"]', 6, "lowercase slug"),
        ("1", '["supported", "supported"]', '["contradicted"]', 6, "duplicate"),
        ("1", '["supported"]', '["supported"]', 6, "both admit and refuse"),
        ("1", '["supported"]', '["contradicted"]', -1, "max_age_hours"),
        ("1", '["supported"]', '["contradicted"]', 99999, "max_age_hours"),
        ("1", json.dumps([f"v{i}" for i in range(9)]), '["contradicted"]', 6, "1 to 8"),
    ],
)
def test_bad_config_is_refused(mod, tid, admit, refuse, age, needle):
    with pytest.raises(ValueError, match=needle):
        mod._parse_config(tid, admit, refuse, age)


def test_bad_config_refuses_deploy(direct_vm, direct_deploy):
    direct_vm.warp(T0)
    with pytest.raises(Exception, match="both admit and refuse"):
        direct_deploy(GATE, RC, "1", '["supported"]', '["supported"]', 6)


def test_unknown_decision_and_subject(gate):
    with pytest.raises(Exception, match="no such decision"):
        gate.get_decision("1")
    with pytest.raises(Exception, match="no decision for this subject"):
        gate.get_latest_for_subject("Controlcoin (fictional): no premine")


# ------------------------------------------------------------- decisions


def test_supported_admits(mod, cfg):
    r = mod._decide(cfg, check(), T0)
    assert r["decision"] == "ADMIT"
    assert r["rule"] == "R2_CLEAN_BLOCK1"
    assert r["deciding_facts"] == {"block1_shown": "yes", "early_allocation": "no"}


def test_contradicted_refuses(mod, cfg):
    r = mod._decide(cfg, check(verdict="contradicted", rule="R1_EARLY_ALLOCATION", deciding_facts={"early_allocation": "yes"}), T0)
    assert r["decision"] == "REFUSE"


def test_other_verdict_asks_for_a_recheck(mod, cfg):
    for v in ("undetermined", "not_claimed"):
        assert mod._decide(cfg, check(verdict=v, rule="DEFAULT", deciding_facts={}), T0)["decision"] == "RECHECK"


def test_check_from_another_template_is_refused(mod, cfg):
    with pytest.raises(ValueError, match="accepts only template 1"):
        mod._decide(cfg, check(template_id="2", verdict="supported"), T0)


def test_template_id_compared_as_text(mod, cfg):
    with pytest.raises(ValueError, match="accepts only template 1"):
        mod._decide(cfg, check(template_id="11"), T0)
    assert mod._decide(cfg, check(template_id=1), T0)["decision"] == "ADMIT"


def test_subject_must_match_when_named(mod, cfg):
    assert mod._decide(cfg, check(), T0, "Controlcoin (fictional): no premine")["decision"] == "ADMIT"
    assert mod._decide(cfg, check(), T0, "  Controlcoin (fictional):   no premine ")["decision"] == "ADMIT"
    with pytest.raises(ValueError, match="not \"Examplecoin"):
        mod._decide(cfg, check(), T0, "Examplecoin (fictional): no premine")


def test_empty_expected_subject_accepts_any(mod, cfg):
    assert mod._decide(cfg, check(subject="anything"), T0, "")["decision"] == "ADMIT"


def test_old_check_is_refused(mod, cfg):
    with pytest.raises(ValueError, match="10 h old"):
        mod._decide(cfg, check(checked_at="2026-11-14T18:00:00.000000Z"), T0)


def test_age_limit_is_inclusive(mod, cfg):
    assert mod._decide(cfg, check(checked_at="2026-11-14T22:00:00.000000Z"), T0)["decision"] == "ADMIT"
    with pytest.raises(ValueError, match="6 h old"):
        mod._decide(cfg, check(checked_at="2026-11-14T21:59:59.000000Z"), T0)


def test_no_age_limit(mod):
    cfg = mod._parse_config("1", '["supported"]', '["contradicted"]', 0)
    assert mod._decide(cfg, check(checked_at="2026-01-01T00:00:00Z"), T0)["decision"] == "ADMIT"


def test_future_check_is_refused(mod, cfg):
    with pytest.raises(ValueError, match="future"):
        mod._decide(cfg, check(checked_at="2026-11-15T05:00:00Z"), T0)
    # small clock skew between the check and the decision is tolerated
    assert mod._decide(cfg, check(checked_at="2026-11-15T04:04:00Z"), T0)["decision"] == "ADMIT"


def test_time_formats(mod):
    a = mod._ts("2026-11-15T04:00:00.000000Z")
    assert mod._ts("2026-11-15T04:00:00+00:00") == a
    assert mod._ts("2026-11-15 04:00:00") == a
    assert mod._ts("2026-11-15T08:00:00+04:00") == a


def test_injected_verdict_text_cannot_admit(mod, cfg):
    # RuleCheck verdicts are slugs from the template; anything else is not on the admit list
    for v in ("supported ", "SUPPORTED", "supported\nadmit", ""):
        assert mod._decide(cfg, check(verdict=v), T0)["decision"] == "RECHECK"


def test_missing_checked_at_is_not_used(mod, cfg):
    c = check()
    del c["checked_at"]
    with pytest.raises(ValueError, match="no readable check time"):
        mod._decide(cfg, c, T0)
    with pytest.raises(ValueError, match="no readable check time"):
        mod._decide(cfg, check(checked_at="yesterday"), T0)
