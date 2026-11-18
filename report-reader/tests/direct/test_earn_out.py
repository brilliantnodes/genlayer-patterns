"""Direct-mode tests for EarnOutExample (examples/consumer).

The direct VM cannot run cross-contract calls, so create() past its first
checks, and settle(), are proven live on Studio and Bradbury. These tests
cover the constructor, the refusals that come before the reader is called
(each credits the value back), withdraw, and the pure functions that create
and settle use: _terms_problem, _seller_share and _settlement. Every company
here is fictional.
"""

import os
import sys

import pytest

from tests.direct.conftest import to_hex

EO = os.environ.get("EO_CONTRACT", "examples/consumer/earn_out_example.py")  # mutation runs point elsewhere
READER = "0x1111111111111111111111111111111111111111"
T0 = "2026-11-20T09:00:00.000000Z"
DIGEST = "ab" * 32
ONE = 10**18


def report():
    return {
        "id": "1",
        "digest": DIGEST,
        "spec": {
            "issuer_name": "Tarnwick Harbour Holdings plc",
            "period_ends": ["2026-11-20 10:00", "2026-11-20 11:00"],
            "figures": [{"key": "revenue"}, {"key": "ltm_ebitda"}],
        },
    }


def reading(status="NOT_DUE", figures=None, digest=DIGEST):
    r = {"report_id": "1", "digest": digest, "period": 0, "status": status, "end": "2026-11-20 10:00", "closes": "2026-11-20 10:40"}
    if figures is not None:
        r["figures"] = figures
    return r


@pytest.fixture
def env(direct_vm, direct_deploy, direct_alice, direct_bob):
    direct_vm.warp(T0)
    c = direct_deploy(EO, READER)

    class E:
        pass

    e = E()
    e.vm, e.c, e.alice, e.bob = direct_vm, c, direct_alice, direct_bob
    return e


@pytest.fixture
def mod(env):
    for m in list(sys.modules.values()):
        if getattr(m, "EarnOutExample", None) is not None and hasattr(m, "_settlement"):
            return m
    raise RuntimeError("contract module not found")


def test_constructor(env):
    t = env.c.totals()
    assert t == {"deals": 0, "locked": "0", "credited": "0", "reader": to_hex(bytes.fromhex(READER[2:]))}


def create(e, value, seller=None, who=None):
    e.vm.sender = who or e.alice
    e.vm.value = value
    try:
        return e.c.create(seller if seller is not None else to_hex(e.bob), "1", DIGEST, 0, "revenue", "10000000", "20000000")
    finally:
        e.vm.value = 0


def test_refusals_before_the_reader_credit_the_value_back(env):
    r = create(env, 0)
    assert r == {"ok": False, "error": "send the GEN to escrow with the call", "refunded": "0"}
    r = create(env, 5 * ONE, seller="not an address")
    assert r["ok"] is False and r["error"] == "seller must be an address" and r["refunded"] == str(5 * ONE)
    r = create(env, 2 * ONE, seller=to_hex(env.alice))
    assert r["error"] == "seller and buyer must differ"
    assert env.c.get_claimable(to_hex(env.alice)) == str(7 * ONE)
    assert env.c.totals()["credited"] == str(7 * ONE) and env.c.totals()["locked"] == "0"


def test_withdraw(env):
    create(env, 3 * ONE, seller="x")
    env.vm.sender = env.alice
    assert env.c.withdraw(ONE) == {"ok": True, "amount": str(ONE), "left": str(2 * ONE)}
    with pytest.raises(Exception, match="amount must be 1 to"):
        env.c.withdraw(5 * ONE)
    with pytest.raises(Exception, match="whole number"):
        env.c.withdraw(True)
    assert env.c.withdraw(0)["amount"] == str(2 * ONE)
    with pytest.raises(Exception, match="nothing to withdraw"):
        env.c.withdraw(0)
    assert env.c.totals()["credited"] == "0"


def test_unknown_deal(env):
    with pytest.raises(Exception, match="no such deal"):
        env.c.get_deal("1")
    with pytest.raises(Exception, match="no such deal"):
        env.c.settle("1")


# ------------------------------------------------------------- pure logic


def test_terms_accepted(mod):
    p, t = mod._terms_problem(report(), reading(), DIGEST, 0, "revenue", "10000000", "20000000")
    assert p == "" and t == {"floor": 10000000, "target": 20000000}
    p, t = mod._terms_problem(report(), reading(), DIGEST, 1, "ltm_ebitda", "-500", "0")
    assert p == "" and t == {"floor": -500, "target": 0}


@pytest.mark.parametrize(
    "args,needle",
    [
        (dict(digest="cd" * 32), "digest is not the one pinned"),
        (dict(digest=None), "digest is not the one pinned"),
        (dict(figure="cash"), "no figure cash"),
        (dict(period=2), "no such period"),
        (dict(period=-1), "no such period"),
        (dict(period=True), "no such period"),
        (dict(period="0"), "no such period"),
        (dict(rd=reading("WAITING")), "already ended (status WAITING)"),
        (dict(rd=reading("OPEN")), "already ended"),
        (dict(rd=reading("READ")), "already ended"),
        (dict(rd=reading("MISSING")), "already ended"),
        (dict(floor="1e6"), "floor must be a whole number"),
        (dict(floor="1.5"), "floor must be a whole number"),
        (dict(floor="007"), "floor must be a whole number"),
        (dict(floor=""), "floor must be a whole number"),
        (dict(floor=True), "floor must be a whole number"),
        (dict(target="9" * 32), "target must be a whole number"),
        (dict(target="2" + "0" * 30), "target is too large"),
        (dict(target="10000000"), "target must be above floor"),
        (dict(target="5"), "target must be above floor"),
    ],
)
def test_terms_refused(mod, args, needle):
    a = dict(digest=DIGEST, period=0, figure="revenue", floor="10000000", target="20000000", rd=reading())
    a.update(args)
    p, t = mod._terms_problem(report(), a["rd"], a["digest"], a["period"], a["figure"], a["floor"], a["target"])
    assert needle in p and t is None


@pytest.mark.parametrize(
    "value,expected",
    [
        (9_000_000, 0),
        (10_000_000, 0),
        (10_000_001, 1),
        (15_000_000, 5_000_000),
        (19_999_999, 9_999_999),
        (20_000_000, 10_000_000),
        (99_000_000, 10_000_000),
        (-5, 0),
    ],
)
def test_seller_share_straight_line_rounded_down(mod, value, expected):
    assert mod._seller_share(10_000_000, 10_000_000, 20_000_000, value) == expected


def test_seller_share_rounds_down_and_never_exceeds(mod):
    assert mod._seller_share(10, 0, 3, 1) == 3  # 10 * 1 // 3
    assert mod._seller_share(10, 0, 3, 2) == 6
    for v in range(-3, 8):
        s = mod._seller_share(7 * ONE, 0, 5, v)
        assert 0 <= s <= 7 * ONE


def deal(**kw):
    d = {"report_id": "1", "digest": DIGEST, "period": 0, "figure": "revenue", "floor": 10_000_000, "target": 20_000_000, "amount": 4 * ONE}
    d.update(kw)
    return d


def test_settlement_read(mod):
    s, b, note = mod._settlement(deal(), reading("READ", {"revenue": "15240000", "ltm_ebitda": "1"}))
    assert s == 4 * ONE * 5_240_000 // 10_000_000 and s + b == 4 * ONE and "15240000" in note


def test_settlement_missing_refunds_buyer(mod):
    assert mod._settlement(deal(), reading("MISSING")) == (0, 4 * ONE, "report missing: escrow back to the buyer")


@pytest.mark.parametrize("st,needle", [("OPEN", "no final answer yet (status OPEN)"), ("NOT_DUE", "status NOT_DUE"), ("WAITING", "status WAITING"), ("CLOSING", "send tick")])
def test_settlement_refuses_until_final(mod, st, needle):
    with pytest.raises(ValueError, match=needle.replace("(", r"\(").replace(")", r"\)")):
        mod._settlement(deal(), reading(st))


def test_settlement_refuses_another_report(mod):
    with pytest.raises(ValueError, match="another report"):
        mod._settlement(deal(), reading("READ", {"revenue": "1"}, digest="cd" * 32))


def test_settlement_refuses_a_malformed_figure(mod):
    with pytest.raises(ValueError, match="figure must be a whole number"):
        mod._settlement(deal(), reading("READ", {"revenue": "15.2"}))
