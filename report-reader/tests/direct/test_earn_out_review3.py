"""EarnOut money paths, third independent review (18 Nov 2026). Asserts
CURRENT behaviour: random sequences of create / accept / cancel / settle /
withdraw against the fake two-state reader, checking after every step that
the contract's books add up and no deal pays twice."""

import random

import pytest

from tests.direct.conftest import to_hex
from tests.direct.test_earn_out import env, mod, create, accept, settle, reading, END_TS, ONE  # noqa: F401


@pytest.mark.parametrize("seed", range(10))
def test_probe3_books_add_up_over_random_sequences(env, seed):
    rnd = random.Random(seed)
    people = [env.alice, env.bob, env.charlie]
    deposited = withdrawn = 0
    paid = {}
    t = END_TS - 1500
    for step in range(70):
        op = rnd.choice(["create", "create", "accept", "cancel", "settle", "withdraw", "flip"])
        t += rnd.choice([0, 30, 60]) if step < 25 else rnd.choice([0, 60, 600])
        env.vm.warp(__import__("tests.direct.test_earn_out", fromlist=["iso"]).iso(t))
        n = int(env.c.totals()["deals"])
        try:
            if op == "create":
                v = rnd.choice([0, 1, ONE, 3 * ONE + 7])
                buyer, seller = rnd.sample(people, 2)
                r = create(env, v, seller=to_hex(seller), who=buyer, floor=str(rnd.randint(-5, 5) * 10**6), target=str(rnd.randint(6, 30) * 10**6),
                           missing=rnd.randint(0, 10000))
                deposited += v
            elif op == "accept" and n:
                did = str(rnd.randint(1, n))
                d = env.c.get_deal(did)
                who = next(p for p in people if to_hex(p).lower() == d["seller"].lower())
                accept(env, did, who=who)
            elif op == "cancel" and n:
                did = str(rnd.randint(1, n))
                d = env.c.get_deal(did)
                env.vm.sender = next(p for p in people if to_hex(p).lower() == d["buyer"].lower())
                env.c.cancel(did)
            elif op == "settle" and n:
                did = str(rnd.randint(1, n))
                before = env.c.get_deal(did)["state"]
                r = settle(env, did)
                d = r["deal"]
                if before in ("OPEN", "OFFERED") and d["state"] in ("SETTLED", "EXPIRED"):
                    assert did not in paid
                    paid[did] = int(d["result"]["to_seller"]) + int(d["result"]["to_buyer"])
                    assert paid[did] == int(d["amount"])
            elif op == "withdraw":
                who = rnd.choice(people)
                env.vm.sender = who
                have = int(env.c.get_claimable(to_hex(who)))
                if have:
                    amt = rnd.choice([0, 1, have])
                    env.c.withdraw(amt)
                    withdrawn += have if amt == 0 else amt
            elif op == "flip":
                st = rnd.choice(["NOT_DUE", "OPEN", "CLOSING", "READ", "MISSING"])
                figs = {"revenue": str(rnd.randint(-10, 40) * 10**6), "ltm_ebitda": "1"} if st == "READ" else None
                past = t >= END_TS
                env.reader.latest = reading(st if past else "NOT_DUE", figs, official=st == "READ" and past, clock=t)
                if rnd.random() < 0.5:
                    env.reader.final = dict(env.reader.latest)
        except Exception:
            pass  # a refused call changes nothing; the books are checked below
        tot = env.c.totals()
        claims = sum(int(env.c.get_claimable(to_hex(p))) for p in people)
        assert int(tot["credited"]) == claims, (step, op, tot)
        assert int(tot["locked"]) + claims == deposited - withdrawn, (step, op, tot, deposited, withdrawn)
    # end phase: the reading is final everywhere; every deal settles once; everyone withdraws; nothing is left
    from tests.direct.test_earn_out import iso as _iso
    t = max(t, END_TS + 7200)
    env.vm.warp(_iso(t))
    value = str(rnd.randint(-10, 40) * 10**6)
    env.reader.latest = reading("READ", {"revenue": value, "ltm_ebitda": "1"}, official=True, clock=t)
    env.reader.final = dict(env.reader.latest)
    for i in range(1, int(env.c.totals()["deals"]) + 1):
        was = env.c.get_deal(str(i))["state"]
        d = settle(env, str(i))["deal"]
        assert d["state"] in ("SETTLED", "EXPIRED", "CANCELLED"), d
        again = settle(env, str(i))["deal"]
        assert again == d  # settling twice changes nothing
        if d["state"] == "SETTLED" and was == "OPEN":
            exp = env.mod._seller_share(int(d["amount"]), int(d["floor"]), int(d["target"]), int(value))
            assert int(d["result"]["to_seller"]) == exp and int(d["result"]["to_seller"]) + int(d["result"]["to_buyer"]) == int(d["amount"])
    for p in people:
        env.vm.sender = p
        have = int(env.c.get_claimable(to_hex(p)))
        if have:
            env.c.withdraw(0)
            withdrawn += have
    tot = env.c.totals()
    assert tot["locked"] == "0" and tot["credited"] == "0" and deposited == withdrawn, (tot, deposited, withdrawn)
