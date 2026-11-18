"""Direct-mode tests for ReportReader. Web pages and the LLM are mocked.

Every company, page and figure here is fictional (Tarnwick Harbour Holdings
plc, Ostravelle Fibre SA).
"""

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

import pytest

from tests.direct.conftest import to_hex

CONTRACT = os.environ.get("RR_CONTRACT", "contracts/report_reader.py")  # mutation runs point elsewhere
PROMPT = r"(?s).*periodic report.*"
URL_T = "https://reports.example/tarnwick/q-{n}.html"
ISSUER = "Tarnwick Harbour Holdings plc"


def ts(s: str) -> int:
    return int(datetime.fromisoformat(s + ":00+00:00").timestamp())


def iso(t: int) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000000Z")


T0 = ts("2026-11-20 09:00")
ENDS = ["2026-11-20 10:00", "2026-11-20 11:00", "2026-11-20 12:00"]
LAG = 10  # minutes
WIN = 30  # minutes
END0 = ts(ENDS[0])
OPEN0 = END0 + LAG * 60
CLOSE0 = OPEN0 + WIN * 60

FIGURES = [
    {"key": "revenue", "label_hint": "Revenue for the period", "labels": ["Revenue"], "ltm": False, "decimals": 0, "step": 1000, "rounding": "down", "sign": "as_printed"},
    {"key": "ltm_ebitda", "label_hint": "EBITDA, last twelve months", "labels": ["EBITDA (last twelve months)", "LTM EBITDA"], "ltm": True, "decimals": 0, "step": 1, "rounding": "down", "sign": "as_printed"},
    {"key": "net_finance_costs", "label_hint": "Net finance costs", "labels": ["Net finance costs", "Net finance income/(costs)", "Finance income"], "ltm": False, "decimals": 0, "step": 1, "rounding": "up", "sign": "finance_cost"},
    {"key": "total_debt", "label_hint": "Total borrowings", "labels": ["Total borrowings"], "ltm": False, "decimals": 0, "step": 1000, "rounding": "up", "sign": "magnitude"},
    {"key": "nav_per_share", "label_hint": "Net asset value per share", "labels": ["Net asset value per share (EUR)"], "ltm": False, "decimals": 2, "step": 1, "rounding": "down", "sign": "as_printed"},
]

PAGE = """Tarnwick Harbour Holdings plc
Quarterly results for the period ended 2026-11-20 10:00 UTC
All figures in EUR thousands unless stated otherwise
Revenue 15,240
EBITDA (last twelve months) 4,180.5
Net finance costs (2,150)
Total borrowings (48,000)
Net asset value per share (EUR) 12.34
"""

FIG_ANSWERS = {
    "revenue": {"value": "15,240", "scale": "thousands", "scale_text": "EUR thousands", "ltm_labelled": "no", "conflicting": "no", "line_label": "Revenue"},
    "ltm_ebitda": {"value": "4,180.5", "scale": "thousands", "scale_text": "EUR thousands", "ltm_labelled": "yes", "conflicting": "no", "line_label": "EBITDA (last twelve months)"},
    "net_finance_costs": {"value": "(2,150)", "scale": "thousands", "scale_text": "EUR thousands", "ltm_labelled": "no", "conflicting": "no", "line_label": "Net finance costs"},
    "total_debt": {"value": "(48,000)", "scale": "thousands", "scale_text": "EUR thousands", "ltm_labelled": "no", "conflicting": "no", "line_label": "Total borrowings"},
    "nav_per_share": {"value": "12.34", "scale": "units", "scale_text": "(EUR)", "ltm_labelled": "no", "conflicting": "no", "line_label": "Net asset value per share (EUR)"},
}
EXPECTED = {"revenue": "15240000", "ltm_ebitda": "4180500", "net_finance_costs": "2150000", "total_debt": "48000000", "nav_per_share": "1234"}


# The tests' own statement of the per-share wording rule, kept apart from the contract's: a share word within
# five words after 'per', or EPS, DPS, NAVPS, BVPS, DPU, NAVPU, '/share', '/unit'.
PER_SHARE_WORDS = ("share", "shares", "unit", "units", "ads", "adr", "adrs", "ordinary", "stapled", "security", "securities", "gdr", "gdrs",
                   "depositary", "depository", "stock")
PER_SHARE_ABBR = ("eps", "dps", "navps", "bvps", "dpu", "navpu")


def reads_per_share(text) -> bool:
    low = " ".join(str(text).lower().split())
    words = "".join(ch if ch.isalnum() else " " for ch in low).split()
    if any(x in words for x in PER_SHARE_ABBR) or "/share" in low or "/unit" in low:
        return True
    return any(w == "per" and any(x in PER_SHARE_WORDS for x in words[k + 1:k + 6]) for k, w in enumerate(words))


def stated(figs):
    """Each figure with per_share stated, as a report's author must: true if a label or the hint reads as per
    share. A figure that already states it, or is not a figure at all (the malformed specs), is left as it is."""
    if not isinstance(figs, list):
        return figs
    out = []
    for f in figs:
        if isinstance(f, dict) and "per_share" not in f:
            texts = [x for x in list(f.get("labels") or []) + [f.get("label_hint", "")] if isinstance(x, str)] if isinstance(f.get("labels"), (list, type(None))) else []
            f = {**f, "per_share": any(reads_per_share(x) for x in texts)}
        out.append(f)
    return out


def spec(**over) -> dict:
    s = {
        "issuer_name": ISSUER,
        "url_template": URL_T,
        "currency": "EUR",
        "period_ends": list(ENDS),
        "publish_lag_minutes": LAG,
        "read_window_minutes": WIN,
        "figures": [dict(f) for f in FIGURES],
    }
    s.update(over)
    s["figures"] = stated(s["figures"])
    return s


def answer(figs=None, drop=(), wrap=True, **top) -> str:
    f = {k: dict(v) for k, v in FIG_ANSWERS.items() if k not in drop}
    for k, v in (figs or {}).items():
        f[k] = {**FIG_ANSWERS.get(k, {}), **f.get(k, {}), **v}
    body = {
        "page_kind": "periodic_report",
        "issuer_name_on_page": ISSUER,
        "period_end_on_page": "2026-11-20 10:00 UTC",
        "currency_on_page": "EUR",
        "marked_draft": "no",
        "decimal_mark": ".",
        "figures": f,
    }
    body.update(top)
    s = json.dumps(body)
    return "```json\n" + s + "\n```" if wrap else s


@pytest.fixture
def env(direct_vm, direct_deploy, direct_alice, direct_bob, direct_charlie):
    direct_vm.warp(iso(T0))
    c = direct_deploy(CONTRACT)

    class E:
        pass

    e = E()
    e.vm, e.c = direct_vm, c
    e.alice, e.bob, e.charlie = direct_alice, direct_bob, direct_charlie
    e.msgs = []  # messages the contract posts (emit); deliver() runs them as the network would

    def hook(vm, req):
        for k in ("PostMessage", "EmitInternalMessage"):  # GenVM v0.2, v0.6
            if isinstance(req, dict) and k in req:
                e.msgs.append(req[k])
                return {"ok": None}
        return None

    direct_vm._gl_call_hook = hook
    return e


def deliver(e, at=None):
    """Run the posted on='finalized' messages as the network does once the
    posting transaction is finalized: sent by the contract to itself."""
    msgs, e.msgs[:] = list(e.msgs), []
    out = []
    for m in msgs:
        assert m["on"] == "finalized" and int(m["value"]) == 0, m
        if at is not None:
            e.vm.warp(iso(at))
        e.vm.sender = e.vm._contract_address
        out.append((meth(m), getattr(e.c, meth(m))(*m["calldata"].get("args", []))))
    return out


def meth(m) -> str:
    """The method a posted message calls (GenVM v0.6 encodes it under '')."""
    cd = m["calldata"]
    return cd["method"] if "method" in cd else cd[""]


@pytest.fixture
def mod(env):
    for m in list(sys.modules.values()):
        if getattr(m, "ReportReader", None) is not None and hasattr(m, "_interpret"):
            return m
    raise RuntimeError("contract module not found")


def register(e, s=None, at=T0, raw=None):
    e.vm.warp(iso(at))
    e.vm.sender = e.alice
    return e.c.register_report(raw if raw is not None else json.dumps(s if s is not None else spec()))


def read(e, llm, rid="1", n=0, at=OPEN0 + 60, page=PAGE, url=None, sender=None):
    e.vm.clear_mocks()
    e.vm.warp(iso(at))
    e.vm.sender = sender or e.bob
    e.vm.mock_web(re.escape(url or URL_T.replace("{n}", str(n))), {"status": 200, "body": page})
    e.vm.mock_llm(PROMPT, llm)
    return e.c.read(rid, n)


def tick(e, rid="1", at=CLOSE0):
    e.vm.warp(iso(at))
    e.vm.sender = e.charlie
    return e.c.tick(rid)


# ------------------------------------------------------------- registration


def test_register_stores_frozen_spec_and_digest(env, mod):
    r = register(env)
    assert r["id"] == "1" and r["owner"] == to_hex(env.alice) and r["created_at"] == T0
    s = r["spec"]
    assert s["issuer_name"] == ISSUER and s["currency"] == "EUR" and s["period_ends"] == ENDS
    assert [f["key"] for f in s["figures"]] == [f["key"] for f in FIGURES]
    assert s["figures"][0]["step"] == "1000" and s["figures"][0]["labels"] == ["revenue"]
    canon = json.dumps(s, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    assert r["digest"] == hashlib.sha256(canon.encode()).hexdigest()
    assert r["periods"][0] == {"period": 0, "end": ENDS[0], "opens": "2026-11-20 10:10", "closes": "2026-11-20 10:40", "url": "https://reports.example/tarnwick/q-0.html"}
    assert env.c.get_report("1") == r
    assert env.c.get_counts() == {"reports": 1, "readings": 0}


def test_digest_is_the_same_for_the_same_terms_however_written(env):
    a = register(env)
    s = spec(issuer_name="  Tarnwick   Harbour Holdings plc ", currency="eur", period_ends=["2026-11-20T10:00", "2026-11-20 11:00:00", "2026-11-20 12:00Z"])
    s["figures"][0] = {**s["figures"][0], "labels": ["  Revenue: ", "REVENUE"], "step": "1000"}
    b = register(env, s)
    assert b["id"] == "2" and a["digest"] == b["digest"] and a["spec"] == b["spec"]


def test_labels_are_normalised_and_deduplicated(env):
    s = spec()
    s["figures"][0]["labels"] = ["Revenue:", " revenue ", "Total revenue"]
    r = register(env, s)
    assert r["spec"]["figures"][0]["labels"] == ["revenue", "total revenue"]


def bad_fig(**over):
    f = dict(FIGURES[0])
    f.update(over)
    return f


@pytest.mark.parametrize(
    "raw,needle",
    [
        ("", "1 to 6000"),
        ("x" * 6001, "1 to 6000"),
        ("{not json", "not valid JSON"),
        ("[1, 2]", "JSON object"),
        (json.dumps({**spec(), "extra": 1}), "unknown field: extra"),
        (json.dumps(spec(issuer_name="")), "issuer_name is required"),
        (json.dumps(spec(issuer_name="A" * 81)), "at most 80"),
        (json.dumps(spec(issuer_name="Bad\x01name")), "one line"),
        (json.dumps(spec(issuer_name="---")), "at least 3 letters"),
        (json.dumps(spec(url_template="https://reports.example/q.html")), "{n} exactly once"),
        (json.dumps(spec(url_template="https://reports.example/{n}/q-{n}.html")), "{n} exactly once"),
        (json.dumps(spec(url_template="https://reports.example/{x}/q-{n}.html")), "no other braces"),
        (json.dumps(spec(url_template="https://reports.example/q-{n}.html?a=1")), "? or #"),
        (json.dumps(spec(url_template="https://reports.example/q-{n}.html#top")), "? or #"),
        (json.dumps(spec(url_template="https://r{n}.example.com/q.html")), "in the path"),
        (json.dumps(spec(url_template="https://10.0.0.1/q-{n}.html")), "public address"),
        (json.dumps(spec(url_template="https://localhost/q-{n}.html")), "public address"),
        (json.dumps(spec(url_template="https://127.0.0.1.nip.io/q-{n}.html")), "public address"),
        (json.dumps(spec(url_template="https://10-0-0-1.reports.example/q-{n}.html")), "public address"),
        (json.dumps(spec(url_template="https://10.0.0.1.reports.example/q-{n}.html")), "public address"),
        (json.dumps(spec(url_template="http://reports.example/q-{n}.html")), "must start with https://"),
        (json.dumps(spec(url_template="https://user@reports.example/q-{n}.html")), "user name"),
        (json.dumps(spec(url_template="ftp://reports.example/q-{n}.html")), "must start with https://"),
        (json.dumps(spec(url_template="https://reports.example/" + "a" * 190 + "{n}")), "at most 200"),
        (json.dumps(spec(currency="XYZ")), "ISO codes"),
        (json.dumps(spec(currency=978)), "ISO codes"),
        (json.dumps(spec(period_ends=[])), "1 to 24"),
        (json.dumps(spec(period_ends=["2026-11-20 10:00"] * 25)), "1 to 24"),
        (json.dumps(spec(period_ends=["2026-11-20 11:00", "2026-11-20 10:00"])), "strictly increasing"),
        (json.dumps(spec(period_ends=["2026-11-20 10:00", "2026-11-20 10:00"])), "strictly increasing"),
        (json.dumps(spec(period_ends=["20 Nov 2026"])), "YYYY-MM-DD HH:MM"),
        (json.dumps(spec(period_ends=["2026-11-20 10:00+04:00"])), "YYYY-MM-DD HH:MM"),
        (json.dumps(spec(period_ends=["2026-11-20 10:00:30"])), "YYYY-MM-DD HH:MM"),
        (json.dumps(spec(period_ends=["2032-01-01 00:00"])), "within five years"),
        (json.dumps(spec(publish_lag_minutes=-1)), "publish_lag_minutes"),
        (json.dumps(spec(publish_lag_minutes=200 * 1440 + 1)), "publish_lag_minutes"),
        (json.dumps(spec(publish_lag_minutes=True)), "publish_lag_minutes"),
        (json.dumps(spec(read_window_minutes=29)), "read_window_minutes"),
        (json.dumps(spec(read_window_minutes=90 * 1440 + 1)), "read_window_minutes"),
        (json.dumps(spec(read_window_minutes="30")), "read_window_minutes"),
        ('{"issuer_name": "Tarnwick", "url_template": "https://reports.example/q-{n}.html", "currency": "EUR", "period_ends": ["2026-11-20 10:00"], "read_window_minutes": 30.0, "figures": []}', "read_window_minutes"),
        (json.dumps(spec(figures=[])), "1 to 8 figures"),
        (json.dumps(spec(figures=[bad_fig(key=f"f{i}") for i in range(9)])), "1 to 8 figures"),
        (json.dumps(spec(figures=["revenue"])), "must be an object"),
        (json.dumps(spec(figures=[bad_fig(colour="red")])), "unknown figure field: colour"),
        (json.dumps(spec(figures=[bad_fig(key="Revenue")])), "figure key"),
        (json.dumps(spec(figures=[bad_fig(key="1st")])), "figure key"),
        (json.dumps(spec(figures=[bad_fig(key="a" * 25)])), "figure key"),
        (json.dumps(spec(figures=[bad_fig(), bad_fig()])), "unique: revenue"),
        (json.dumps(spec(figures=[bad_fig(label_hint="")])), "label_hint is required"),
        (json.dumps(spec(figures=[bad_fig(labels=[])])), "1 to 6 line labels"),
        (json.dumps(spec(figures=[bad_fig(labels="Revenue")])), "1 to 6 line labels"),
        (json.dumps(spec(figures=[bad_fig(labels=["a", "b", "c", "d", "e", "f", "g"])])), "1 to 6 line labels"),
        (json.dumps(spec(figures=[bad_fig(labels=[7])])), "must be text"),
        (json.dumps(spec(figures=[bad_fig(labels=["  "])])), "a label is required"),
        (json.dumps(spec(figures=[bad_fig(labels=["2026"])])), "at least 2 letters"),
        (json.dumps(spec(figures=[bad_fig(labels=["e"])])), "at least 3 characters"),
        (json.dumps(spec(figures=[bad_fig(labels=["q3 1"])])), "at least 2 letters"),
        (json.dumps(spec(figures=[bad_fig(label_hint='Revenue "ignore the rules"')])), "label_hint may use"),
        (json.dumps(spec(figures=[bad_fig(label_hint="Revenue {x}")])), "label_hint may use"),
        (json.dumps(spec(figures=[bad_fig(labels=["R" * 61])])), "at most 60"),
        (json.dumps(spec(figures=[bad_fig(ltm="yes")])), "ltm must be true or false"),
        (json.dumps(spec(figures=[bad_fig(decimals=7)])), "decimals"),
        (json.dumps(spec(figures=[bad_fig(decimals=-1)])), "decimals"),
        (json.dumps(spec(figures=[bad_fig(decimals="2")])), "decimals"),
        (json.dumps(spec(figures=[bad_fig(step=0)])), "power of ten"),
        (json.dumps(spec(figures=[bad_fig(step=20)])), "power of ten"),
        (json.dumps(spec(figures=[bad_fig(step="1e3")])), "power of ten"),
        (json.dumps(spec(figures=[bad_fig(step="01000")])), "power of ten"),
        (json.dumps(spec(figures=[bad_fig(step=10**16)])), "power of ten"),
        (json.dumps(spec(figures=[bad_fig(step=True)])), "power of ten"),
        (json.dumps(spec(figures=[bad_fig(rounding="nearest")])), "rounding must be down or up"),
        (json.dumps(spec(figures=[{k: v for k, v in FIGURES[0].items() if k != "rounding"}])), "rounding must be down or up"),
        (json.dumps(spec(figures=[bad_fig(sign="cost")])), "sign must be"),
    ],
)
def test_register_refuses_bad_specs(env, raw, needle):
    with pytest.raises(Exception, match=re.escape(needle)):
        register(env, raw=raw)
    assert env.c.get_counts()["reports"] == 0


def test_defaults_for_optional_figure_fields(env):
    s = spec(figures=[{"key": "revenue", "label_hint": "Revenue", "labels": ["Revenue"], "rounding": "down"}])
    f = register(env, s)["spec"]["figures"][0]
    assert f == {"key": "revenue", "label_hint": "Revenue", "labels": ["revenue"], "ltm": False, "decimals": 0, "step": "1", "rounding": "down", "sign": "as_printed",
                 "per_share": False}


def test_unknown_report_and_bad_period(env):
    register(env)
    for bad in ("2", "", "0"):
        with pytest.raises(Exception, match="no such report"):
            env.c.get_report(bad)
    for n in (-1, 3, True):
        with pytest.raises(Exception, match="period must be"):
            env.c.get_reading("1", n, OPEN0)
    with pytest.raises(Exception, match="at must be"):
        env.c.get_reading("1", 0, -5)


# ------------------------------------------------------------------ reading


def test_read_table_page(env):
    register(env)
    r = read(env, answer())
    assert r["kind"] == "READ" and r["figures"] == EXPECTED and r["attempt"] == 1
    g = env.c.get_reading("1", 0, OPEN0 + 60)
    assert g["status"] == "READ" and g["final"] and g["figures"] == EXPECTED
    assert g["read_by"] == to_hex(env.bob) and g["url"] == "https://reports.example/tarnwick/q-0.html" and g["read_at"] == OPEN0 + 60
    assert g["units"]["nav_per_share"] == {"decimals": 2, "step": "1", "rounding": "down", "sign": "as_printed", "per_share": True}
    assert env.c.get_counts() == {"reports": 1, "readings": 1}


def test_only_one_official_reading(env):
    register(env)
    read(env, answer())
    with pytest.raises(Exception, match="already has its official reading"):
        read(env, answer(figs={"revenue": {"value": "15,999"}}), at=OPEN0 + 300)
    assert env.c.get_reading("1", 0, CLOSE0 + 1)["figures"]["revenue"] == "15240000"


def test_not_published_binds_nothing_then_read(env):
    register(env)
    r = read(env, answer(page_kind="not_published"), page="Tarnwick Harbour Holdings plc: results for this period are not yet published.")
    assert r["kind"] == "NOT_PUBLISHED" and "figures" not in r
    assert env.c.get_reading("1", 0, OPEN0 + 120)["status"] == "OPEN"
    r2 = read(env, answer(), at=OPEN0 + 600)
    assert r2["kind"] == "READ" and r2["attempt"] == 2
    a = env.c.get_attempts("1", 0)
    assert a["count"] == 2 and [x["kind"] for x in a["kept"]] == ["NOT_PUBLISHED", "READ"]


def test_window_and_status_timeline(env):
    register(env)
    g = lambda at: env.c.get_reading("1", 0, at)["status"]
    assert g(END0 - 1) == "NOT_DUE"
    assert g(END0) == "WAITING" and g(OPEN0 - 1) == "WAITING"
    assert g(OPEN0) == "OPEN" and g(CLOSE0 - 1) == "OPEN"
    assert g(CLOSE0) == "CLOSING"  # nothing processed at or after the close yet
    with pytest.raises(Exception, match="opens at 2026-11-20 10:10"):
        read(env, answer(), at=OPEN0 - 1)
    t = tick(env, at=CLOSE0)
    assert t["missing"] == [0] and t["clock"] == CLOSE0
    assert g(CLOSE0) == "MISSING" and env.c.get_reading("1", 0, CLOSE0)["final"]
    assert g(CLOSE0 - 1) == "OPEN"  # as of an earlier time the window was open; MISSING is final from the close


def test_read_after_close_settles_missing_without_reading(env):
    register(env)
    r = read(env, answer(), at=CLOSE0)
    assert r["kind"] == "CLOSED" and r["status"] == "MISSING"
    assert env.c.get_reading("1", 0, CLOSE0 + 5)["status"] == "MISSING"
    assert env.c.get_attempts("1", 0)["count"] == 0 and env.c.get_counts()["readings"] == 0


def test_clock_never_runs_backwards(env):
    """A READ stamped before the close but processed after a later-stamped
    write is handled at the later time: it cannot land after MISSING."""
    register(env)
    tick(env, at=CLOSE0 + 60)
    assert env.c.get_reading("1", 0, CLOSE0 + 60)["status"] == "MISSING"
    r = read(env, answer(), at=CLOSE0 - 300)
    assert r["kind"] == "CLOSED"
    assert env.c.get_reading("1", 0, CLOSE0 + 60)["status"] == "MISSING"


def test_clock_moved_by_another_period_also_closes(env):
    register(env)
    end1 = ts(ENDS[1])
    read(env, answer(period_end_on_page="2026-11-20 11:00 UTC"), n=1, at=end1 + LAG * 60 + 30)
    assert env.c.get_reading("1", 0, CLOSE0)["status"] == "MISSING"


def test_reading_seen_as_of_an_earlier_time_is_not_yet_read(env):
    register(env)
    read(env, answer(), at=OPEN0 + 300)
    assert env.c.get_reading("1", 0, OPEN0 + 299)["status"] == "OPEN"
    assert env.c.get_reading("1", 0, OPEN0 + 300)["status"] == "READ"
    assert env.c.get_reading("1", 0, CLOSE0 + 999)["status"] == "READ"


def test_each_period_has_its_own_page_and_window(env):
    register(env)
    end2 = ts(ENDS[2])
    page2 = PAGE.replace("2026-11-20 10:00", "2026-11-20 12:00").replace("15,240", "16,010")
    r = read(env, answer(figs={"revenue": {"value": "16,010"}}, period_end_on_page="2026-11-20 12:00 UTC"), n=2, at=end2 + LAG * 60, page=page2)
    assert r["figures"]["revenue"] == "16010000"
    assert env.c.get_reading("1", 1, end2)["status"] == "MISSING"  # period 1 closed at 11:40 and the clock is past it


def test_publish_lag_zero(env):
    register(env, spec(publish_lag_minutes=0))
    assert env.c.get_reading("1", 0, END0)["status"] == "OPEN"
    assert read(env, answer(), at=END0)["kind"] == "READ"


# ------------------------------------------------------------- conversions


@pytest.mark.parametrize(
    "value,rounding,decimals,step,expected",
    [
        ("1,234,567.891", "down", 0, 1000, 1234000),
        ("1,234,567.891", "up", 0, 1000, 1235000),
        ("1,234,567.891", "down", 2, 1, 123456789),
        ("1,234,567.891", "up", 2, 1, 123456790),
        ("(1,500.5)", "down", 0, 1000, -2000),
        ("(1,500.5)", "up", 0, 1000, -1000),
        ("-1,500.5", "down", 0, 1, -1501),
        ("−1,500.5", "up", 0, 1, -1500),
        ("1,000", "down", 0, 1000, 1000),
        ("0.5", "down", 0, 1, 0),
        ("0.5", "up", 0, 1, 1),
        ("EUR 1,000", "down", 0, 1, 1000),
        ("€1,000", "down", 0, 1, 1000),
        ("1,000 EUR", "down", 0, 1, 1000),
    ],
)
def test_rounding_in_one_step(env, value, rounding, decimals, step, expected):
    # a per-share figure: the only kind read in whole units (totals never are)
    s = spec(figures=[{"key": "x", "label_hint": "X", "labels": ["Measure X per share"], "decimals": decimals, "step": step, "rounding": rounding, "sign": "as_printed"}])
    register(env, s)
    page = f"{ISSUER}\nperiod ended 2026-11-20 10:00 UTC\nEUR\nMeasure X per share (EUR) {value}\n"
    r = read(env, answer(figs={"x": {"value": value, "scale": "units", "scale_text": "(EUR)", "line_label": "Measure X per share"}}, drop=list(FIG_ANSWERS)), page=page)
    assert r["kind"] == "READ", r
    assert r["figures"]["x"] == str(expected)


def test_millions_in_prose(env):
    s = spec(figures=[{"key": "revenue", "label_hint": "Revenue", "labels": ["Revenue for the quarter was"], "decimals": 0, "step": 100000, "rounding": "down"}])
    register(env, s)
    page = f"{ISSUER}. Highlights for the quarter ended 2026-11-20 10:00 UTC, in EUR.\nRevenue for the quarter was EUR 12.45 million.\n"
    llm = answer(figs={"revenue": {"value": "EUR 12.45 million", "scale": "millions", "scale_text": "million", "line_label": "Revenue for the quarter was"}}, drop=list(FIG_ANSWERS))
    r = read(env, llm, page=page)
    assert r.get("figures", {}).get("revenue") == "12400000", r


def test_label_in_the_middle_of_a_sentence_is_not_anchored(env):
    s = spec(figures=[{"key": "revenue", "label_hint": "Revenue", "labels": ["Revenue for the quarter was"], "decimals": 0, "step": 100000, "rounding": "down"}])
    register(env, s)
    page = f"{ISSUER}. For the quarter ended 2026-11-20 10:00 UTC, in EUR, segment revenue for the quarter was EUR 12.45 million.\n"
    llm = answer(figs={"revenue": {"value": "EUR 12.45 million", "scale": "millions", "scale_text": "million", "line_label": "Revenue for the quarter was"}}, drop=list(FIG_ANSWERS))
    nr(read(env, llm, page=page), "N2_NOT_ANCHORED")


@pytest.mark.parametrize(
    "label,value,expected",
    [
        ("Net finance costs", "(2,150)", "2150000"),
        ("Net finance costs", "2,150", "2150000"),
        ("Net finance income/(costs)", "(2,150)", "2150000"),
        ("Net finance income/(costs)", "2,150", "-2150000"),
        ("Finance income", "2,150", None),
    ],
)
def test_finance_cost_sign_rule(env, label, value, expected):
    register(env)
    page = PAGE.replace("Net finance costs (2,150)", f"{label} {value}")
    r = read(env, answer(figs={"net_finance_costs": {"value": value, "line_label": label}}), page=page)
    if expected is None:
        assert r["kind"] == "NO_READING" and r["reason"] == "N2_FINANCE_LABEL"
    else:
        assert r["kind"] == "READ" and r["figures"]["net_finance_costs"] == expected


def test_magnitude_ignores_brackets(env):
    register(env)
    page = PAGE.replace("Total borrowings (48,000)", "Total borrowings 48,000")
    r = read(env, answer(figs={"total_debt": {"value": "48,000"}}), page=page)
    assert r["figures"]["total_debt"] == "48000000"


# ---------------------------------------------------------- refused copies


def nr(r, reason):
    assert r["kind"] == "NO_READING", r
    assert r["reason"] == reason, r


@pytest.mark.parametrize(
    "top,reason",
    [
        (dict(page_kind="other"), "N1_WRONG_PAGE"),
        (dict(page_kind="compliance_report"), "N1_WRONG_PAGE"),
        (dict(issuer_name_on_page="Tarnwick Harbour"), "N1_WRONG_PAGE"),
        (dict(issuer_name_on_page="Ostravelle Fibre SA"), "N1_WRONG_PAGE"),
        (dict(issuer_name_on_page=""), "N1_WRONG_PAGE"),
        (dict(marked_draft="yes"), "N3_NOT_FINAL"),
        (dict(period_end_on_page="2026-11-20 11:00 UTC"), "N2_WRONG_PERIOD"),
        (dict(period_end_on_page="2026-11-20 14:00 +04:00"), "N2_WRONG_PERIOD"),
        (dict(period_end_on_page="2026-11-20"), "N2_WRONG_PERIOD"),
        (dict(period_end_on_page=""), "N2_WRONG_PERIOD"),
        (dict(currency_on_page="USD"), "N2_CURRENCY"),
        (dict(currency_on_page="EUR / USD"), "N2_CURRENCY"),
        (dict(currency_on_page="£"), "N2_CURRENCY"),
        (dict(decimal_mark=","), "N2_FORMAT"),
        (dict(figures="none"), "N2_FIGURE_MISSING"),
    ],
)
def test_page_level_refusals(env, top, reason):
    register(env)
    nr(read(env, answer(**top)), reason)


def test_issuer_name_with_punctuation_and_more_words_matches(env):
    register(env)
    assert read(env, answer(issuer_name_on_page="TARNWICK HARBOUR HOLDINGS PLC (the Group)"))["kind"] == "READ"


def test_issuer_name_must_be_whole_words(env):
    register(env, spec(issuer_name="Tarn"))
    nr(read(env, answer(issuer_name_on_page=ISSUER)), "N1_WRONG_PAGE")


def test_date_only_period_end_for_a_midnight_end(env):
    register(env, spec(period_ends=["2026-12-31 00:00"] if False else ["2027-01-01 00:00"], publish_lag_minutes=0))
    end = ts("2027-01-01 00:00")
    page = PAGE.replace("2026-11-20 10:00 UTC", "31 December 2026")
    assert read(env, answer(period_end_on_page="2026-12-31"), at=end + 60, page=page)["kind"] == "READ"


@pytest.mark.parametrize(
    "key,over,reason",
    [
        ("revenue", {"value": ""}, "N2_FIGURE_MISSING"),
        ("revenue", {"value": None}, "N2_FIGURE_MISSING"),
        ("revenue", {"conflicting": "yes"}, "N2_CONFLICT"),
        ("ltm_ebitda", {"ltm_labelled": "no"}, "N2_NOT_LTM"),
        ("revenue", {"line_label": "Other revenue"}, "N2_LABEL"),
        ("ltm_ebitda", {"line_label": "Adjusted EBITDA"}, "N2_LABEL"),
        ("revenue", {"value": "15,250"}, "N2_NOT_ANCHORED"),
        ("revenue", {"value": "5,240"}, "N2_NOT_ANCHORED"),
        ("revenue", {"value": "15,24"}, "N2_NOT_ANCHORED"),
        ("revenue", {"scale": "not_stated"}, "N2_UNITS_MISSING"),
        ("revenue", {"scale": "millions"}, "N2_UNITS_MISSING"),
        ("revenue", {"scale_text": ""}, "N2_UNITS_MISSING"),
        ("revenue", {"scale_text": "EUR millions"}, "N2_UNITS_MISSING"),
        ("revenue", {"scale": "units", "scale_text": "EUR thousands"}, "N2_UNITS_MISSING"),
        ("nav_per_share", {"scale": "thousands"}, "N2_UNITS_MISSING"),
    ],
)
def test_figure_level_refusals(env, key, over, reason):
    register(env)
    nr(read(env, answer(figs={key: over})), reason)


def test_missing_figure_key(env):
    register(env)
    nr(read(env, answer(drop=["total_debt"])), "N2_FIGURE_MISSING")


def test_value_far_from_its_label_is_not_anchored(env):
    register(env)
    page = PAGE.replace("Revenue 15,240", "Revenue" + " filler" * 30 + " 15,240")
    nr(read(env, answer(), page=page), "N2_NOT_ANCHORED")


def test_value_inside_a_longer_number_is_not_anchored(env):
    register(env)
    page = PAGE.replace("Revenue 15,240", "Revenue 215,240")
    nr(read(env, answer(), page=page), "N2_NOT_ANCHORED")
    page = PAGE.replace("Revenue 15,240", "Revenue 15,240.7")
    nr(read(env, answer(), page=page, at=OPEN0 + 120), "N2_NOT_ANCHORED")


def test_label_must_be_printed(env):
    s = spec()
    s["figures"][0]["labels"] = ["Revenue", "Group revenue"]
    register(env, s)
    nr(read(env, answer(figs={"revenue": {"line_label": "Group revenue"}})), "N2_NOT_ANCHORED")


def test_anchoring_tolerates_case_spacing_and_colon(env):
    register(env)
    page = PAGE.replace("Revenue 15,240", "REVENUE:   15,240")
    assert read(env, answer(figs={"revenue": {"line_label": "REVENUE:"}}), page=page)["kind"] == "READ"


def scale_ok(mod, page, line, scale_text, mult, code="EUR", value=None):
    lines = mod._page_lines(page)
    return mod._scale_ok(lines, mod._norm(line), scale_text, mult, code, value)


def test_scale_words(env, mod):
    assert scale_ok(mod, "Figures in EUR'000\nRevenue 15,240", "Revenue 15,240", "EUR'000", 10**3)
    assert scale_ok(mod, "In €m\nRevenue 15.2", "Revenue 15.2", "€m", 10**6)
    assert scale_ok(mod, "EURm\nRevenue 15.2", "Revenue 15.2", "EURm", 10**6)
    assert scale_ok(mod, "EUR bn\nRevenue 1.5", "Revenue 1.5", "EUR bn", 10**9)
    assert not scale_ok(mod, "Figures in EUR\nRevenue 15,240", "Revenue 15,240", "EUR", 1)  # totals are never read in whole units
    assert not scale_ok(mod, "Figures in EUR\nRevenue 15,240", "Revenue 15,240", "EUR", 10**3)
    assert not scale_ok(mod, "EUR thousands and EUR millions\nRevenue 15,240", "Revenue 15,240", "EUR thousands and EUR millions", 10**3)
    assert not scale_ok(mod, "EUR thousands\nRevenue 15,240", "Revenue 15,240", "USD thousands", 10**3)


def test_scale_on_the_figures_line_decides(env, mod):
    page = "All figures in EUR thousands\nRevenue 15,240\nTotal borrowings (EUR million) 48.0"
    assert scale_ok(mod, page, "Total borrowings (EUR million) 48.0", "EUR million", 10**6)
    assert not scale_ok(mod, page, "Total borrowings (EUR million) 48.0", "EUR thousands", 10**3)  # the heading does not apply to this line
    assert not scale_ok(mod, page, "Revenue 15,240", "EUR thousands", 10**3)  # two heading scales: which applies is not printed
    assert not scale_ok(mod, page, "Total borrowings (EUR million) 48.0", "EUR", 1)  # units on a line that names millions
    two = "Debt (EUR million; prior year EUR thousands) 48.0"
    assert not scale_ok(mod, "Debt\n" + two, two, "EUR million", 10**6)  # the line names two scales
    assert scale_ok(mod, "Revenue: EUR 16.2 million", "Revenue: EUR 16.2 million", "million", 10**6, value="EUR 16.2 million")
    assert scale_ok(mod, "Revenue: EUR 16.2 million", "Revenue: EUR 16.2 million", "million", 10**6, value="16.2")  # the word after the value
    assert not scale_ok(mod, "Revenue: EUR 16.2 million", "Revenue: EUR 16.2 million", "EUR", 1, value="EUR 16.2 million")


def test_scale_words_must_be_whole_words_and_the_only_heading_scale(env, mod):
    page = "Tarnwick Harbour Holdings plc\nAll figures in EUR thousands\nRevenue 15,240"
    assert not scale_ok(mod, page, "Revenue 15,240", "m", 10**6)  # 'm' is not printed as a word
    assert not scale_ok(mod, page, "Revenue 15,240", "EUR", 1)  # units under a thousands heading
    assert not scale_ok(mod, page + "\nSee the bond terms in EUR millions", "Revenue 15,240", "EUR millions", 10**6)
    assert scale_ok(mod, page + "\nThe bond of EUR 2.5 million was repaid", "Revenue 15,240", "EUR thousands", 10**3)  # an amount's own scale is not a heading


@pytest.mark.parametrize("mark", ["£000", "GBP 000", "GBP'000", "£'000", "000s"])
def test_thousands_marks(env, mod, mark):
    page = f"All figures in {mark}\nRevenue 15,240"
    assert scale_ok(mod, page, "Revenue 15,240", mark, 10**3, "GBP")
    assert not scale_ok(mod, page, "Revenue 15,240", mark, 1, "GBP")


def test_numbers_are_not_thousands_marks(env, mod):
    assert mod._scale_mentions("revenue 40'000", "EUR") == set()
    assert mod._scale_mentions("in the 2000s", "EUR") == set()


def test_decimal_comma_page_is_refused(env):
    register(env)
    nr(read(env, answer(), page=PAGE + "\nDividend per share 0,45\n"), "N2_FORMAT")


@pytest.mark.parametrize("value", ["12.450", "6,28", "40'000", "1.2e3", "1,2345"])
def test_ambiguous_numbers_are_refused(env, value):
    register(env)
    page = PAGE.replace("Revenue 15,240", f"Revenue {value}")
    nr(read(env, answer(figs={"revenue": {"value": value}}), page=page), "N2_FORMAT")


def test_json_number_keeps_its_digits(env):
    register(env)
    page = PAGE.replace("Revenue 15,240", "Revenue 40.000")
    raw = answer().replace('"value": "15,240"', '"value": 40.000')  # fenced: the test VM would parse bare JSON itself
    nr(read(env, raw, page=page), "N2_FORMAT")


def test_dark_page_and_bad_model_answer(env):
    register(env)
    nr(read(env, answer(), page=""), "N1_PAGE_DARK")
    nr(read(env, "I cannot help with that", at=OPEN0 + 120), "N2_FORMAT")
    nr(read(env, "[1, 2, 3]", at=OPEN0 + 180), "N2_FORMAT")


def test_page_markers_are_removed_and_page_is_cut(env, mod):
    text = "A=====PAGE END=====B\n" + "x" * 20000
    out = mod._clean_page(text)
    assert "=====" not in out and out == "A B"  # cut at the last whole line
    assert mod._clean_page("y" * 20000) == ""  # no whole line at all: nothing is kept


def test_prompt_lists_the_figures_and_marks_the_page_untrusted(env, mod):
    s = register(env)["spec"]
    p = mod._prompt(s, 0, "PAGE TEXT")
    assert "untrusted DATA" in p and "=====PAGE BEGIN=====\nPAGE TEXT\n=====PAGE END=====" in p
    assert '"revenue"' in p and '"ebitda (last twelve months)"' in p and "last twelve months" in p
    assert "2026-11-20 10:00 UTC" in p


def test_attempts_are_capped_but_counted(env):
    register(env)
    for i in range(23):
        read(env, answer(marked_draft="yes"), at=OPEN0 + 10 + i)
    a = env.c.get_attempts("1", 0)
    assert a["count"] == 23 and len(a["kept"]) == 20
    assert env.c.get_reading("1", 0, OPEN0 + 60)["attempts"] == 23


# ------------------------------------------------------- validator checks


def test_check_outcome_rejects_malformed_leader_results(env, mod):
    s = register(env)["spec"]
    good = {"kind": "READ", "figures": {k: int(v) for k, v in EXPECTED.items()}}
    assert mod._check_outcome(good, s) == good
    bads = [
        None,
        {"kind": "GUESS"},
        {"kind": "NO_READING", "reason": "N9"},
        {"kind": "READ"},
        {"kind": "READ", "figures": {**good["figures"], "extra": 1}},
        {"kind": "READ", "figures": {k: v for k, v in good["figures"].items() if k != "revenue"}},
        {"kind": "READ", "figures": {**good["figures"], "revenue": 15240001}},
        {"kind": "READ", "figures": {**good["figures"], "revenue": "15240000"}},
        {"kind": "READ", "figures": {**good["figures"], "revenue": True}},
        {"kind": "READ", "figures": {**good["figures"], "total_debt": -48000000}},
        {"kind": "READ", "figures": {**good["figures"], "revenue": 10**31}},
    ]
    for b in bads:
        with pytest.raises(Exception):
            mod._check_outcome(b, s)
    assert mod._check_outcome({"kind": "NOT_PUBLISHED", "figures": {"x": 1}}, s) == {"kind": "NOT_PUBLISHED"}


def test_same_outcome_is_exact(env, mod):
    a = {"kind": "READ", "figures": {"revenue": 1000}}
    assert mod._same_outcome(a, {"kind": "READ", "figures": {"revenue": 1000}})
    assert not mod._same_outcome(a, {"kind": "READ", "figures": {"revenue": 2000}})
    assert not mod._same_outcome(a, {"kind": "NOT_PUBLISHED"})
    assert mod._same_outcome({"kind": "NO_READING", "reason": "N2_FORMAT"}, {"kind": "NO_READING", "reason": "N2_FORMAT"})
    assert not mod._same_outcome({"kind": "NO_READING", "reason": "N2_FORMAT"}, {"kind": "NO_READING", "reason": "N2_LABEL"})


def test_two_copies_that_round_alike_agree(env, mod):
    s = register(env)["spec"]
    a = mod._interpret(s, 0, json.loads(answer(wrap=False)), PAGE)
    page2 = PAGE.replace("Revenue 15,240", "Revenue 15,240.4")
    b = mod._interpret(s, 0, json.loads(answer(wrap=False, figs={"revenue": {"value": "15,240.4"}})), page2)
    assert a["kind"] == b["kind"] == "READ" and mod._same_outcome(a, b)


# -------------------------------------------------------------- listings


def test_get_reports_and_rules(env):
    register(env)
    register(env, spec(issuer_name="Ostravelle Fibre SA", url_template="https://reports.example/ostravelle/{n}.html"))
    rows = env.c.get_reports(1, 10)
    assert [r["id"] for r in rows] == ["1", "2"] and rows[1]["issuer_name"] == "Ostravelle Fibre SA"
    assert env.c.get_reports(2, 1)[0]["id"] == "2" and env.c.get_reports(5, 5) == []
    rules = env.c.get_rules()
    assert rules["final_statuses"] == ["READ", "MISSING"] and "N2_NOT_ANCHORED" in rules["no_reading_reasons"]


# --------------------------------------------- the validator, run directly


def leader_then(e, leader_llm, mine_llm, page=PAGE, mine_page=None, at=OPEN0 + 60):
    register(e)
    r = read(e, leader_llm, page=page, at=at)
    e.vm.clear_mocks()
    e.vm.mock_web(re.escape(URL_T.replace("{n}", "0")), {"status": 200, "body": mine_page if mine_page is not None else page})
    e.vm.mock_llm(PROMPT, mine_llm)
    return r


def test_validator_agrees_on_the_same_copy(env):
    leader_then(env, answer(), answer())
    assert env.vm.run_validator() is True


def test_validator_agrees_when_digits_below_the_step_differ(env):
    page2 = PAGE.replace("Revenue 15,240", "Revenue 15,240.4")
    leader_then(env, answer(), answer(figs={"revenue": {"value": "15,240.4"}}), mine_page=page2)
    assert env.vm.run_validator() is True


def test_validator_rejects_one_unit_off(env):
    page2 = PAGE.replace("EBITDA (last twelve months) 4,180.5", "EBITDA (last twelve months) 4,180.6")
    leader_then(env, answer(), answer(figs={"ltm_ebitda": {"value": "4,180.6"}}), mine_page=page2)
    assert env.vm.run_validator() is False


def test_validator_rejects_a_wrong_scale(env):
    page2 = PAGE.replace("EUR thousands", "EUR millions")
    mine = answer(figs={k: {"scale": "millions", "scale_text": "EUR millions"} for k in ("revenue", "ltm_ebitda", "net_finance_costs", "total_debt")})
    leader_then(env, answer(), mine, mine_page=page2)
    assert env.vm.run_validator() is False


def test_validator_rejects_a_read_when_it_sees_no_reading(env):
    leader_then(env, answer(), answer(marked_draft="yes"))
    assert env.vm.run_validator() is False


def test_validator_rejects_a_value_its_own_page_does_not_show(env):
    leader_then(env, answer(), answer(), mine_page=PAGE.replace("Revenue 15,240", "Revenue 15,999"))
    assert env.vm.run_validator() is False


def test_validator_agrees_on_the_same_no_reading_reason(env):
    leader_then(env, answer(marked_draft="yes"), answer(marked_draft="yes"))
    assert env.vm.run_validator() is True


def test_validator_rejects_another_no_reading_reason(env):
    leader_then(env, answer(marked_draft="yes"), answer(currency_on_page="USD"))
    assert env.vm.run_validator() is False


def test_validator_rejects_a_tampered_or_failed_leader(env):
    leader_then(env, answer(), answer())
    tampered = {"kind": "READ", "figures": {**{k: int(v) for k, v in EXPECTED.items()}, "revenue": 99000000}}
    assert env.vm.run_validator(leader_result=tampered) is False
    assert env.vm.run_validator(leader_result={"kind": "READ"}) is False
    assert env.vm.run_validator(leader_result={"kind": "NO_READING", "reason": "MADE_UP"}) is False
    assert env.vm.run_validator(leader_error=Exception("boom")) is False


def test_tick_lists_only_closed_periods_without_a_read(env):
    register(env)
    read(env, answer())
    t = tick(env, at=ts(ENDS[1]) + LAG * 60 + WIN * 60)
    assert t["missing"] == [1]


def test_a_value_without_digits_is_not_anchored(env):
    register(env)
    page = PAGE.replace("Revenue 15,240", "Revenue nil")
    nr(read(env, answer(figs={"revenue": {"value": "nil"}}), page=page), "N2_NOT_ANCHORED")


def test_json_number_on_the_page_reads_with_its_digits(env):
    register(env)
    raw = answer().replace('"value": "12.34"', '"value": 12.34')  # fenced: the test VM would parse bare JSON itself
    r = read(env, raw)
    assert r["kind"] == "READ" and r["figures"]["nav_per_share"] == "1234", r.get("reason")
