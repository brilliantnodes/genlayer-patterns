"""The reader marks its answers finalized itself. read() and the writes
that close a window post a message to the contract with on='finalized'; the
network runs it only once the posting transaction is finalized (appeals
included), and only the contract itself may send it. A consumer pays only on
an answer marked "finalized". Measured on Studio first: a view of another
contract's finalized state (StorageType.LATEST_FINAL) hit the 600 s leader
timeout, while a self-message posted on='finalized' ran right after
finalization, and an outside call to it was refused. Fictional company.
"""

import pytest

from tests.direct.test_report_reader import (  # noqa: F401
    env, mod, iso, register, read, tick, deliver, meth, answer, OPEN0, CLOSE0, END0,
)


def reading(e, n=0, at=None):
    return e.c.get_reading("1", n, at if at is not None else CLOSE0 + 3600)


def test_a_read_is_marked_finalized_only_when_its_message_runs(env):
    register(env)
    r = read(env, answer())
    assert r["kind"] == "READ"
    g = reading(env)
    assert g["status"] == "READ" and g["final"] is True and g["finalized"] is False
    assert [meth(m) for m in env.msgs] == ["confirm_read"]
    out = deliver(env, at=OPEN0 + 120)
    assert out == [("confirm_read", {"ok": True, "report_id": "1", "period": 0})]
    assert reading(env)["finalized"] is True


def test_a_no_reading_posts_nothing(env):
    register(env)
    r = read(env, answer(), page="Maintenance")
    assert r["kind"] == "NO_READING" and env.msgs == []


def test_confirm_read_with_another_reading_marks_nothing(env):
    register(env)
    read(env, answer())
    m = env.msgs.pop()
    env.vm.sender = env.vm._contract_address
    assert env.c.confirm_read("1", 0, "00" * 32)["ok"] is False  # a reading an appeal replaced
    assert reading(env)["finalized"] is False
    assert env.c.confirm_read(*m["calldata"]["args"])["ok"] is True


@pytest.mark.parametrize("call", [lambda c: c.confirm_read("1", 0, "00" * 32), lambda c: c.confirm_clock("1", CLOSE0 + 5)])
def test_only_the_contract_itself_can_confirm(env, call):
    register(env)
    for who in (env.alice, env.bob, env.charlie):
        env.vm.sender = who
        with pytest.raises(Exception, match="only this contract"):
            call(env.c)


def test_missing_is_marked_finalized_when_the_closing_write_is_finalized(env):
    register(env)
    tick(env, at=CLOSE0 + 10)
    g = reading(env)
    assert g["status"] == "MISSING" and g["finalized"] is False
    assert [(meth(m), m["calldata"]["args"]) for m in env.msgs] == [("confirm_clock", ["1", CLOSE0 + 10])]
    deliver(env, at=CLOSE0 + 60)
    g = reading(env)
    assert g["finalized"] is True and g["final_clock"] == CLOSE0 + 10
    assert reading(env, 1, at=END0)["finalized"] is False  # another period is not affected


def test_a_write_that_closes_no_window_posts_nothing(env):
    register(env)
    tick(env, at=OPEN0 + 10)
    assert env.msgs == []


def test_a_closed_read_that_closes_a_window_posts_confirm_clock(env):
    register(env)
    r = read(env, answer(), at=CLOSE0 + 30)
    assert r["kind"] == "CLOSED" and [meth(m) for m in env.msgs] == ["confirm_clock"]


def test_a_window_already_read_posts_no_confirm_clock(env):
    register(env)
    read(env, answer())
    deliver(env)
    tick(env, at=CLOSE0 + 10)  # period 0 has its READ: nothing to mark
    assert env.msgs == []


def test_the_finalized_clock_never_runs_back(env):
    register(env)
    env.vm.sender = env.vm._contract_address
    env.c.confirm_clock("1", CLOSE0 + 50)
    assert env.c.confirm_clock("1", CLOSE0 + 10)["final_clock"] == CLOSE0 + 50
    with pytest.raises(Exception, match="whole number"):
        env.c.confirm_clock("1", "1")


def test_a_finalized_clock_before_the_close_is_not_missing_for_good(env):
    register(env)
    env.vm.sender = env.vm._contract_address
    env.c.confirm_clock("1", CLOSE0 - 1)
    tick(env, at=CLOSE0 + 10)
    assert reading(env)["finalized"] is False
