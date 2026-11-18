"""Direct-mode tests for EarnOutExample (examples/consumer).

The direct VM cannot run cross-contract calls, so these tests replace
gl.get_contract_at with a fake ReportReader. The fake keeps the reader's
latest state and, apart, the answer the network has finalized; like the
real reader (confirm_read, confirm_clock) it reports "finalized": true only
once the latest answer is the finalized one, and it records which state each
call read. That runs create, accept, cancel and settle end to end, and
proves that every call reads the latest state (a reading not yet finalized
still blocks create and accept) while settle pays only on an answer marked
finalized. The live runs on Studio use the real reader. Every company here is
fictional.
"""

import os
import sys
from datetime import datetime, timezone

import pytest

from tests.direct.conftest import to_hex

EO = os.environ.get("EO_CONTRACT", "examples/consumer/earn_out_example.py")  # mutation runs point elsewhere
READER = "0x1111111111111111111111111111111111111111"
T0 = "2026-11-20T09:00:00.000000Z"
END = "2026-11-20 10:00"
END_TS = int(datetime.fromisoformat("2026-11-20T10:00:00+00:00").timestamp())
DIGEST = "ab" * 32
ONE = 10**18


def iso(t: int) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000000Z")


def report():
    return {
        "id": "1",
        "digest": DIGEST,
        "spec": {
            "issuer_name": "Tarnwick Harbour Holdings plc",
            "period_ends": [END, "2026-11-20 11:00"],
            "figures": [{"key": "revenue"}, {"key": "ltm_ebitda"}],
        },
    }


def reading(status="NOT_DUE", figures=None, digest=DIGEST, period=0, official=False, clock=END_TS - 3600, finalized=None):
    r = {"report_id": "1", "digest": digest, "period": period, "status": status, "end": END, "end_ts": END_TS + 3600 * period,
         "closes": "2026-11-20 10:40", "has_official": official, "clock": clock}
    if finalized is not None:
        r["finalized"] = finalized
    if figures is not None:
        r["figures"] = figures
    return r


class FakeReader:
    """A ReportReader whose latest answer is marked finalized only when the
    network's finalized answer (`final`) is the same one."""

    def __init__(self):
        self.latest = reading()
        self._final = reading()
        self.calls = []  # (method, state)
        self.fail = False

    @property
    def final(self):
        return self._final

    @final.setter
    def final(self, r):
        """The network finalized this answer: it is also the latest one."""
        self._final = dict(r)
        self.latest = dict(r)

    def view(self, state=None):
        outer = self

        class V:
            def get_report(self, rid):
                outer.calls.append(("get_report", state))
                if outer.fail or rid != "1":
                    raise Exception("no such report")
                return report()

            def get_reading(self, rid, period, at):
                outer.calls.append(("get_reading", state))
                if outer.fail or rid != "1":
                    raise Exception("no such report")
                out = dict(outer.latest)
                fin = outer.final
                out["finalized"] = out.get("status") in ("READ", "MISSING") and all(fin.get(k) == out.get(k) for k in ("status", "figures", "digest", "period"))
                return out

        return V()


@pytest.fixture
def env(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie, monkeypatch):
    direct_vm.warp(T0)
    c = direct_deploy(EO, READER)
    fake = FakeReader()
    mod = next(m for m in list(sys.modules.values()) if getattr(m, "EarnOutExample", None) is not None and hasattr(m, "_settlement"))
    if hasattr(getattr(mod.gl, "contract", None), "get_at"):
        monkeypatch.setattr(mod.gl.contract, "get_at", lambda addr: fake)  # the GenVM v0.6 build
    else:
        monkeypatch.setattr(mod.gl, "get_contract_at", lambda addr: fake)

    class E:
        pass

    e = E()
    e.vm, e.c, e.alice, e.bob, e.charlie, e.reader, e.mod = direct_vm, c, direct_alice, direct_bob, direct_charlie, fake, mod
    return e


@pytest.fixture
def mod(env):
    return env.mod


def create(e, value, seller=None, who=None, period=0, figure="revenue", floor="10000000", target="20000000", missing=5000, digest=DIGEST, rid="1", at=None):
    if at is not None:
        e.vm.warp(iso(at))
    e.vm.sender = who or e.alice
    e.vm.value = value
    try:
        return e.c.create(seller if seller is not None else to_hex(e.bob), rid, digest, period, figure, floor, target, missing)
    finally:
        e.vm.value = 0


def accept(e, did="1", digest=None, who=None, at=None):
    if at is not None:
        e.vm.warp(iso(at))
    e.vm.sender = who or e.bob
    return e.c.accept(did, digest if digest is not None else e.c.get_deal(did)["terms_digest"])


def settle(e, did="1", at=None):
    if at is not None:
        e.vm.warp(iso(at))
    e.vm.sender = e.charlie
    return e.c.settle(did)


def claim(e, who):
    return int(e.c.get_claimable(to_hex(who)))


def check_totals(e, locked):
    t = e.c.totals()
    assert int(t["locked"]) == locked, t
    return t


# ------------------------------------------------------------ the full path


def test_constructor(env):
    t = env.c.totals()
    assert t == {"deals": 0, "locked": "0", "credited": "0", "reader": to_hex(bytes.fromhex(READER[2:]))}


def test_create_accept_settle_read(env):
    r = create(env, 4 * ONE)
    assert r["ok"] is True
    d = r["deal"]
    assert d["state"] == "OFFERED" and d["amount"] == str(4 * ONE) and d["missing_seller_bp"] == 5000 and d["period_end_ts"] == END_TS
    assert len(d["terms_digest"]) == 64
    assert env.reader.calls and all(s is None for _, s in env.reader.calls)  # create reads the latest state
    check_totals(env, 4 * ONE)
    assert accept(env)["deal"]["state"] == "OPEN"
    env.reader.calls.clear()
    env.reader.latest = reading("READ", {"revenue": "15240000", "ltm_ebitda": "1"}, official=True, clock=END_TS + 900)
    with pytest.raises(Exception, match="not finalized on the network yet"):
        settle(env, at=END_TS + 900)  # read, but not finalized yet
    assert env.reader.calls == [("get_reading", None)]  # settle reads the latest state, and the reader's finalized mark
    env.reader.final = dict(env.reader.latest)
    d = settle(env, at=END_TS + 1000)["deal"]
    to_seller = 4 * ONE * 5_240_000 // 10_000_000
    assert d["state"] == "SETTLED" and d["result"]["to_seller"] == str(to_seller) and d["result"]["to_buyer"] == str(4 * ONE - to_seller)
    assert claim(env, env.bob) == to_seller and claim(env, env.alice) == 4 * ONE - to_seller
    check_totals(env, 0)
    assert settle(env)["deal"]["state"] == "SETTLED"  # settling twice changes nothing
    assert claim(env, env.bob) == to_seller


@pytest.mark.parametrize("bp,to_seller", [(0, 0), (5000, 2 * ONE), (10000, 4 * ONE), (3333, 4 * ONE * 3333 // 10000)])
def test_missing_pays_the_pinned_share(env, bp, to_seller):
    create(env, 4 * ONE, missing=bp)
    accept(env)
    env.reader.final = reading("MISSING", official=False, clock=END_TS + 3000)
    d = settle(env, at=END_TS + 3000)["deal"]
    assert d["result"]["to_seller"] == str(to_seller) and d["result"]["to_buyer"] == str(4 * ONE - to_seller) and f"{bp} bp" in d["result"]["note"]
    check_totals(env, 0)


def test_closing_and_open_refuse_until_final(env):
    create(env, ONE)
    accept(env)
    for st in ("NOT_DUE", "WAITING", "OPEN"):
        env.reader.final = reading(st)
        with pytest.raises(Exception, match=f"status {st}"):
            settle(env)
    env.reader.final = reading("CLOSING")
    with pytest.raises(Exception, match="send tick"):
        settle(env)
    check_totals(env, ONE)


def test_settle_refuses_another_report_or_period(env):
    create(env, ONE)
    accept(env)
    env.reader.final = reading("READ", {"revenue": "1"}, digest="cd" * 32)
    with pytest.raises(Exception, match="another report or period"):
        settle(env)


# ---------------------------------------------------------- offer and accept


def test_only_the_seller_accepts_the_exact_terms(env):
    create(env, ONE)
    with pytest.raises(Exception, match="only the seller"):
        accept(env, who=env.charlie)
    with pytest.raises(Exception, match="terms_digest is not the one"):
        accept(env, digest="00" * 32)
    accept(env)
    with pytest.raises(Exception, match="not OFFERED"):
        accept(env)


@pytest.mark.parametrize("change,needle", [
    (dict(latest=reading("WAITING")), "already ended"),
    (dict(latest=reading(official=True)), "already exists"),
    (dict(latest=reading(clock=END_TS)), "at or after the period end"),
    (dict(at=END_TS), "already ended"),
])
def test_accept_refuses_once_the_outcome_can_be_known(env, change, needle):
    create(env, ONE)
    if "latest" in change:
        env.reader.latest = change["latest"]
    with pytest.raises(Exception, match=needle):
        accept(env, at=change.get("at"))
    assert env.c.get_deal("1")["state"] == "OFFERED"


def test_buyer_cancels_an_offer_not_accepted(env):
    create(env, 3 * ONE)
    env.vm.sender = env.bob
    with pytest.raises(Exception, match="only the buyer"):
        env.c.cancel("1")
    env.vm.sender = env.alice
    d = env.c.cancel("1")["deal"]
    assert d["state"] == "CANCELLED" and d["result"]["to_buyer"] == str(3 * ONE)
    assert claim(env, env.alice) == 3 * ONE
    check_totals(env, 0)
    with pytest.raises(Exception, match="only an offer not yet accepted"):
        env.c.cancel("1")
    with pytest.raises(Exception, match="not OFFERED"):
        accept(env)


def test_accepted_deal_cannot_be_cancelled(env):
    create(env, ONE)
    accept(env)
    env.vm.sender = env.alice
    with pytest.raises(Exception, match="only an offer not yet accepted"):
        env.c.cancel("1")


def test_offer_never_accepted_goes_back_at_settle(env):
    create(env, 2 * ONE)
    with pytest.raises(Exception, match="not accepted yet"):
        settle(env, at=END_TS - 1)
    d = settle(env, at=END_TS)["deal"]
    assert d["state"] == "EXPIRED" and claim(env, env.alice) == 2 * ONE and claim(env, env.bob) == 0
    check_totals(env, 0)
    with pytest.raises(Exception, match="not OFFERED"):
        accept(env)


# -------------------------------------------------------- create refusals


def test_refusals_before_the_reader_credit_the_value_back(env):
    r = create(env, 0)
    assert r == {"ok": False, "error": "send the GEN to escrow with the call", "refunded": "0"}
    r = create(env, 5 * ONE, seller="not an address")
    assert r["ok"] is False and r["error"] == "seller must be an address" and r["refunded"] == str(5 * ONE)
    r = create(env, 2 * ONE, seller=to_hex(env.alice))
    assert r["error"] == "seller and buyer must differ"
    r = create(env, ONE, period=True)
    assert r["error"] == "period must be a whole number"
    assert claim(env, env.alice) == 8 * ONE
    assert env.c.totals()["credited"] == str(8 * ONE) and env.c.totals()["locked"] == "0"


def test_reader_refusal_credits_the_value_back(env):
    env.reader.fail = True
    r = create(env, ONE)
    assert r["ok"] is False and "reader refused" in r["error"] and claim(env, env.alice) == ONE


@pytest.mark.parametrize("latest,needle", [
    (reading(official=True), "already exists"),
    (reading(clock=END_TS + 1), "at or after the period end"),
    (reading("READ", {"revenue": "1"}, official=True), "already ended"),
])
def test_create_refuses_a_period_whose_outcome_can_be_known(env, latest, needle):
    env.reader.latest = latest
    r = create(env, ONE)
    assert r["ok"] is False and needle in r["error"] and claim(env, env.alice) == ONE
    assert env.c.totals()["deals"] == 0


def test_create_refuses_after_the_period_end_by_its_own_time(env):
    r = create(env, ONE, at=END_TS)
    assert r["ok"] is False and "already ended" in r["error"]


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
    with pytest.raises(Exception, match="no such deal"):
        env.c.accept("1", "00")


# ------------------------------------------------------------- pure logic


NOW = END_TS - 600


def test_terms_accepted(mod):
    p, t = mod._terms_problem(report(), reading(), DIGEST, 0, "revenue", "10000000", "20000000", 0, NOW)
    assert p == "" and t == {"floor": 10000000, "target": 20000000, "missing_seller_bp": 0, "period_end_ts": END_TS}
    p, t = mod._terms_problem(report(), reading(period=1), DIGEST, 1, "ltm_ebitda", "-500", "0", 10000, NOW)
    assert p == "" and t["floor"] == -500 and t["missing_seller_bp"] == 10000


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
        (dict(rd=reading(period=1)), "another report or period"),
        (dict(rd=reading(digest="cd" * 32)), "another report or period"),
        (dict(rd=reading("WAITING")), "already ended (status WAITING)"),
        (dict(rd=reading("OPEN")), "already ended"),
        (dict(rd=reading("READ")), "already ended"),
        (dict(rd=reading("MISSING")), "already ended"),
        (dict(rd=reading(official=True)), "already exists"),
        (dict(rd=reading(official=None)), "already exists"),
        (dict(rd=reading(clock=END_TS)), "at or after the period end"),
        (dict(rd=reading(clock=True)), "at or after the period end"),
        (dict(rd={**reading(), "end_ts": None}), "no period end"),
        (dict(now=END_TS), "already ended"),
        (dict(floor="1e6"), "floor must be a whole number"),
        (dict(floor="1.5"), "floor must be a whole number"),
        (dict(floor="007"), "floor must be a whole number"),
        (dict(floor=""), "floor must be a whole number"),
        (dict(floor=True), "floor must be a whole number"),
        (dict(target="9" * 32), "target must be a whole number"),
        (dict(target="2" + "0" * 30), "target is too large"),
        (dict(target="10000000"), "target must be above floor"),
        (dict(target="5"), "target must be above floor"),
        (dict(missing=-1), "missing_seller_bp"),
        (dict(missing=10001), "missing_seller_bp"),
        (dict(missing="5000"), "missing_seller_bp"),
        (dict(missing=True), "missing_seller_bp"),
    ],
)
def test_terms_refused(mod, args, needle):
    a = dict(digest=DIGEST, period=0, figure="revenue", floor="10000000", target="20000000", rd=reading(), missing=0, now=NOW)
    a.update(args)
    p, t = mod._terms_problem(report(), a["rd"], a["digest"], a["period"], a["figure"], a["floor"], a["target"], a["missing"], a["now"])
    assert needle in p and t is None


def test_terms_digest_covers_parties_and_every_term(mod):
    terms = {"report_id": "1", "digest": DIGEST, "period": 0, "figure": "revenue", "floor": 1, "target": 2, "missing_seller_bp": 0, "amount": 5}
    base = mod._terms_digest("0xA", "0xB", terms)
    assert base == mod._terms_digest("0xa", "0xb", dict(reversed(list(terms.items()))))
    assert base != mod._terms_digest("0xA", "0xC", terms)
    for k in terms:
        assert base != mod._terms_digest("0xA", "0xB", {**terms, k: "x"}), k


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
    d = {"report_id": "1", "digest": DIGEST, "period": 0, "figure": "revenue", "floor": 10_000_000, "target": 20_000_000, "missing_seller_bp": 2500, "amount": 4 * ONE}
    d.update(kw)
    return d


def test_settlement_read(mod):
    s, b, note = mod._settlement(deal(), reading("READ", {"revenue": "15240000", "ltm_ebitda": "1"}, finalized=True))
    assert s == 4 * ONE * 5_240_000 // 10_000_000 and s + b == 4 * ONE and "15240000" in note


def test_settlement_missing_pays_the_pinned_share(mod):
    assert mod._settlement(deal(), reading("MISSING", finalized=True)) == (ONE, 3 * ONE, "report missing: 2500 bp to the seller")
    assert mod._settlement(deal(missing_seller_bp=0, amount=7), reading("MISSING", finalized=True))[:2] == (0, 7)
    assert mod._settlement(deal(missing_seller_bp=3333, amount=7), reading("MISSING", finalized=True))[:2] == (2, 5)


@pytest.mark.parametrize("st", ["READ", "MISSING"])
@pytest.mark.parametrize("fin", [None, False, "true", 1])
def test_settlement_pays_only_on_an_answer_marked_finalized(mod, st, fin):
    with pytest.raises(ValueError, match="not finalized on the network yet"):
        mod._settlement(deal(), reading(st, {"revenue": "15240000"}, finalized=fin))


@pytest.mark.parametrize("st,needle", [("OPEN", "no final answer yet (status OPEN)"), ("NOT_DUE", "status NOT_DUE"), ("WAITING", "status WAITING"), ("CLOSING", "send tick")])
def test_settlement_refuses_until_final(mod, st, needle):
    with pytest.raises(ValueError, match=needle.replace("(", r"\(").replace(")", r"\)")):
        mod._settlement(deal(), reading(st))


def test_settlement_refuses_another_report_or_period(mod):
    with pytest.raises(ValueError, match="another report or period"):
        mod._settlement(deal(), reading("READ", {"revenue": "1"}, digest="cd" * 32))
    with pytest.raises(ValueError, match="another report or period"):
        mod._settlement(deal(), reading("READ", {"revenue": "1"}, period=1))


def test_settlement_refuses_a_malformed_figure(mod):
    with pytest.raises(ValueError, match="figure must be a whole number"):
        mod._settlement(deal(), reading("READ", {"revenue": "15.2"}, finalized=True))
