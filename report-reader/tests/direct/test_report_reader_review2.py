"""Regression tests for the weak points found by the second independent
review of 18 Nov 2026. Pages are shaped like Studio's measured render of
mode="text": one line per table row, cells joined by one space, prose lines
kept as lines. Every company, page and figure here is fictional.
"""

import json
import re

import pytest

from tests.direct.test_report_reader import env, mod, iso  # noqa: F401
from tests.direct.test_report_reader_review import (  # noqa: F401
    TAR, E0, SITE, PROMPT, BASE_FIGS, TARNWICK_RENDERED, T_FIGS, OP_FIGS, live_spec, fig, ans, run, refused,
)

HEAD = (f"{TAR}\nQuarterly results\n\nResults for the quarter ended 2026-11-18 08:15 UTC.\n\n"
        "{heading}\n\nQuarter ended 2026-11-18 08:15 UTC Prior quarter ended 2026-08-19 08:15 UTC\n")
TAIL = "\n\nFictional company and figures. Not investment information."
HL = f"{TAR}\nQuarterly highlights\nHighlights for the quarter ended 2026-11-18 08:15 UTC. All amounts in euros (EUR).\n"


def page(rows, heading="All figures in EUR thousands unless stated otherwise.", extra="", header=None):
    h = HEAD.replace("{heading}", heading) if header is None else header
    return h + "\n".join(rows) + "\n" + extra + TAIL


def read_ok(r, key, value):
    assert r["kind"] == "READ", r
    assert r["figures"][key] == value, r


def one(key, label, **kw):
    f = {"key": key, "label_hint": label, "labels": [label], "ltm": False, "decimals": 0, "step": 1, "rounding": "down", "sign": "as_printed"}
    f.update(kw)
    return [f]


OP_ROWS = ["Revenue 15,240 14,880"]


# ---------------------------------------------------------------- the sign


@pytest.mark.parametrize("cell", ["-€1,200", "–€1,200", "−€1,200", "-EUR 1,200", "(€1,200)"])
def test_sign_before_the_currency_is_the_values(env, cell):
    p = page(OP_ROWS + [f"Operating profit/(loss) {cell} 900"])
    refused(run(env, live_spec(figs=OP_FIGS), p, ans(TAR, {"operating_profit": fig("1,200", "Operating profit/(loss)")})), "N2_NOT_ANCHORED")
    r = run(env, live_spec(figs=OP_FIGS), p, ans(TAR, {"operating_profit": fig(cell, "Operating profit/(loss)")}))
    read_ok(r, "operating_profit", "-1200000")


def test_sign_before_the_currency_in_a_highlights_line(env):
    hl = HL + "Operating profit/(loss): –EUR 1.2 million\n"
    refused(run(env, live_spec(figs=OP_FIGS), hl, ans(TAR, {"operating_profit": fig("1.2 million", "Operating profit/(loss)", "millions", "million")})), "N2_NOT_ANCHORED")
    r = run(env, live_spec(figs=OP_FIGS), hl, ans(TAR, {"operating_profit": fig("–EUR 1.2 million", "Operating profit/(loss)", "millions", "million")}))
    read_ok(r, "operating_profit", "-1200000")


@pytest.mark.parametrize("dash", ["—", "‒", "－", "﹣", "―"])
def test_every_minus_glyph_is_a_minus(env, dash):
    p = page(OP_ROWS + [f"Operating profit/(loss) {dash}1,200 900"])
    read_ok(run(env, live_spec(figs=OP_FIGS), p, ans(TAR, {"operating_profit": fig(f"{dash}1,200", "Operating profit/(loss)")})), "operating_profit", "-1200000")
    refused(run(env, live_spec(figs=OP_FIGS), p, ans(TAR, {"operating_profit": fig("1,200", "Operating profit/(loss)")})), "N2_NOT_ANCHORED")


def test_an_opening_bracket_before_the_value_is_its_sign(env, mod):
    assert mod._anchored(mod._page_lines("Revenue (1,200"), "revenue", "1,200", "EUR") is None  # even with the closing bracket lost


def test_spaced_dash_is_refused_either_way(env):
    p = page(["Operating profit/(loss) - 1,200 900"])  # a minus, or an empty cell then 1,200
    refused(run(env, live_spec(figs=OP_FIGS), p, ans(TAR, {"operating_profit": fig("1,200", "Operating profit/(loss)")})), "N2_NOT_ANCHORED")
    refused(run(env, live_spec(figs=OP_FIGS), p, ans(TAR, {"operating_profit": fig("- 1,200", "Operating profit/(loss)")})), "N2_FORMAT")


# ---------------------------------------------------- the first amount


@pytest.mark.parametrize("row", ["Net finance costs – (2,040)", "Net finance costs - (2,040)", "Net finance costs — (2,040)"])
def test_empty_dash_cell_never_reads_the_next_column(env, row):
    p = page(["Revenue 15,240 14,880", row])
    figs = [BASE_FIGS[0], BASE_FIGS[2]]
    refused(run(env, live_spec(figs=figs), p, ans(TAR, {"revenue": fig("15,240", "Revenue"), "net_finance_costs": fig("(2,040)", "Net finance costs")})), "N2_NOT_ANCHORED")


@pytest.mark.parametrize("line,change", [
    ("Revenue increased by EUR 1.3 million to EUR 16.2 million", "EUR 1.3 million"),
    ("Revenue up EUR 1.3 million to EUR 16.2 million", "EUR 1.3 million"),
    ("Revenue rose EUR 1.3 million", "EUR 1.3 million"),
    ("Revenue fell by EUR 1.3 million", "EUR 1.3 million"),
])
def test_a_change_is_not_the_figure(env, line, change):
    figs = [{**BASE_FIGS[0], "step": 1}]
    refused(run(env, live_spec(figs=figs), HL + line + "\n", ans(TAR, {"revenue": fig(change, "Revenue", "millions", "million")})), "N2_NOT_ANCHORED")


@pytest.mark.parametrize("line,value", [
    ("Revenue rose 9% to EUR 16.2 million", "EUR 16.2 million"),
    ("Revenue for the quarter was EUR 16.2 million", "EUR 16.2 million"),
    ("Revenue: EUR 16.2 million", "EUR 16.2 million"),
])
def test_level_after_linking_words_reads(env, line, value):
    figs = [{**BASE_FIGS[0], "step": 1}]
    read_ok(run(env, live_spec(figs=figs), HL + line + "\n", ans(TAR, {"revenue": fig(value, "Revenue", "millions", "million")})), "revenue", "16200000")


@pytest.mark.parametrize("sym", ["$", "£", "¥"])
def test_an_amount_in_another_currency_is_not_read(env, sym):
    hl = HL + f"Revenue {sym}16.2 million (€15.0 million)\n"
    figs = [{**BASE_FIGS[0], "step": 1}]
    refused(run(env, live_spec(figs=figs), hl, ans(TAR, {"revenue": fig("16.2 million", "Revenue", "millions", "million")})), "N2_NOT_ANCHORED")


# -------------------------------------------------------------- the scale


def test_another_amounts_scale_on_the_line_does_not_decide(env):
    cash = one("cash", "Cash and cash equivalents", step=1000)
    p = page(["Revenue 15,240 14,880", "Cash and cash equivalents 15,240 14,880 of which EUR 2.5 million restricted"])
    read_ok(run(env, live_spec(figs=cash), p, ans(TAR, {"cash": fig("15,240", "Cash and cash equivalents")})), "cash", "15240000")
    refused(run(env, live_spec(figs=cash), p, ans(TAR, {"cash": fig("15,240", "Cash and cash equivalents", "millions", "million")})), "N2_UNITS_MISSING")


def test_per_share_figures_never_take_the_heading_scale(env):
    eps = one("eps", "Earnings per share", decimals=2)
    heading = "All figures in EUR thousands, except per share amounts."
    p = page(["Revenue 15,240 14,880", "Earnings per share 1.23 1.10"], heading=heading)
    refused(run(env, live_spec(figs=eps), p, ans(TAR, {"eps": fig("1.23", "Earnings per share")})), "N2_UNITS_MISSING")
    refused(run(env, live_spec(figs=eps), p, ans(TAR, {"eps": fig("1.23", "Earnings per share", "units", "EUR")})), "N2_UNITS_MISSING")  # 'EUR' is not on its line
    nav = one("nav", "Net asset value per share (EUR)", decimals=2)
    p = page(["Revenue 15,240 14,880", "Net asset value per share (EUR) 12.34 12.10"], heading=heading)
    read_ok(run(env, live_spec(figs=nav), p, ans(TAR, {"nav": fig("12.34", "Net asset value per share (EUR)", "units", "(EUR)")})), "nav", "1234")


def test_the_page_is_cut_at_a_line_break(env, mod):
    head = f"{TAR}\nResults for the quarter ended 2026-11-18 08:15 UTC.\nAll figures in EUR thousands unless stated otherwise.\n"
    line = "Revenue: EUR 16.2"
    body = head + "x" * (mod.PAGE_CHARS - len(head) - len(line) - 2) + "\n" + line + " million\nEnd\n"
    assert mod._clean_page(body).endswith("x")  # the half line is gone
    refused(run(env, live_spec(figs=[BASE_FIGS[0]]), body, ans(TAR, {"revenue": fig("EUR 16.2", "Revenue")})), "N2_NOT_ANCHORED")


@pytest.mark.parametrize("line,millions_page", [
    ("The results call starts at 10:00 a.m. UTC.", False),
    ("Webcast replay available from 3 p.m.", False),
    ("Our M&A pipeline remains strong.", False),
    ("I'm pleased with the quarter, said the chief executive.", False),
    ("Over a million passengers travelled with us.", False),
    ("Chief Financial Officer: Anna K. Smith", True),
    ("Employees may join the 401(k) plan.", True),
    ("We now serve thousands of customers.", True),
])
def test_an_ordinary_line_names_no_heading_scale(env, line, millions_page):
    m_figs = {k: {**v, "scale": "millions", "scale_text": "EUR millions"} for k, v in T_FIGS.items()}
    base, figs = (TARNWICK_RENDERED.replace("EUR thousands", "EUR millions"), m_figs) if millions_page else (TARNWICK_RENDERED, T_FIGS)
    p = base.replace("The board approved", line + "\nThe board approved")
    assert run(env, live_spec(), p, ans(TAR, figs))["kind"] == "READ"


@pytest.mark.parametrize("heading,mult", [
    ("All figures in EUR thousands", 10**3), ("In €m", 10**6), ("EURm", 10**6), ("Figures in thousands of euros", 10**3),
    ("Amounts in millions", 10**6), ("EUR'000", 10**3), ("£000", 10**3),
])
def test_headings_still_name_their_scale(env, mod, heading, mult):
    assert mod._heading_scales(mod._norm(heading), "EUR" if "£" not in heading else "GBP") == {mult}


# ------------------------------------------------------------- LTM, footnotes


def test_ltm_must_be_printed_on_the_figures_line(env):
    figs = one("ltm_ebitda", "EBITDA", ltm=True, step=1000)
    p = page(["Revenue 15,240 14,880", "EBITDA 1,050.0 4,180.5"],
             header=(f"{TAR}\nResults for the quarter ended 2026-11-18 08:15 UTC.\nAll figures in EUR thousands.\nQ3 2026 LTM to 2026-11-18 08:15 UTC\n"))
    refused(run(env, live_spec(figs=figs), p, ans(TAR, {"ltm_ebitda": fig("1,050.0", "EBITDA", ltm="yes")})), "N2_NOT_LTM")


@pytest.mark.parametrize("row", ["Revenue¹ 15,240 14,880", "Revenue (a) 15,240 14,880", "Revenue² ³ 15,240 14,880"])
def test_footnote_marks_are_skipped(env, row):
    p = TARNWICK_RENDERED.replace("Revenue 15,240 14,880", row)
    read_ok(run(env, live_spec(), p, ans(TAR, T_FIGS)), "revenue", "15240000")


# ------------------------------------------------------------- the period


@pytest.mark.parametrize("zone", ["EST", "+04:00", "CET", "-05:00"])
def test_period_end_in_another_zone_is_refused(env, zone):
    p = TARNWICK_RENDERED.replace("2026-11-18 08:15 UTC", f"2026-11-18 08:15 {zone}")
    refused(run(env, live_spec(), p, ans(TAR, T_FIGS)), "N2_WRONG_PERIOD")


def test_next_quarters_page_is_refused(env):
    nxt = TARNWICK_RENDERED.replace("Results for the quarter ended 2026-11-18 08:15 UTC.", "Results for the quarter ended 2027-02-17 08:15 UTC.") \
        .replace("Quarter ended 2026-11-18 08:15 UTC Prior quarter ended 2026-08-19 08:15 UTC", "Quarter ended 2027-02-17 08:15 UTC Prior quarter ended 2026-11-18 08:15 UTC") \
        .replace("Revenue 15,240 14,880", "Revenue 16,010 15,240")
    refused(run(env, live_spec(), nxt, ans(TAR, {**T_FIGS, "revenue": fig("16,010", "Revenue")})), "N2_WRONG_PERIOD")


# ---------------------------------------------------------------- URLs


@pytest.mark.parametrize("url", ["https://localhost.localdomain/q-{n}.html", "https://make-127-0-0-1-rr.1u.ms/q-{n}.html", "https://7f000001.c0a80001.rbndr.us/q-{n}.html"])
def test_more_private_names_are_refused(env, url):
    env.vm.warp(iso(E0 - 1800))
    env.vm.sender = env.alice
    with pytest.raises(Exception, match="public address"):
        env.c.register_report(json.dumps({**live_spec(), "url_template": url}))


def test_page_urls_one_per_period(env):
    spec = {k: v for k, v in live_spec().items() if k != "url_template"}
    spec["page_urls"] = [f"{SITE}/x/q3-2026.html"]
    env.vm.warp(iso(E0 - 1800))
    env.vm.sender = env.alice
    r = env.c.register_report(json.dumps(spec))
    assert r["spec"]["page_urls"] == [f"{SITE}/x/q3-2026.html"] and "url_template" not in r["spec"]
    env.vm.clear_mocks()
    env.vm.warp(iso(E0 + 6 * 60))
    env.vm.sender = env.bob
    env.vm.mock_web(re.escape(f"{SITE}/x/q3-2026.html"), {"status": 200, "body": TARNWICK_RENDERED})
    env.vm.mock_llm(PROMPT, ans(TAR, T_FIGS))
    out = env.c.read(r["id"], 0)
    assert out["kind"] == "READ" and out["figures"]["revenue"] == "15240000", out


def test_page_urls_each_period_reads_its_own_page(env):
    spec = {k: v for k, v in live_spec().items() if k != "url_template"}
    spec["period_ends"] = ["2026-11-18 08:15", "2026-11-18 08:45"]
    spec["page_urls"] = [f"{SITE}/x/q3-2026.html", f"{SITE}/x/q4-2026.html"]
    env.vm.warp(iso(E0 - 1800))
    env.vm.sender = env.alice
    rid = env.c.register_report(json.dumps(spec))["id"]
    page1 = TARNWICK_RENDERED.replace("2026-11-18 08:15 UTC", "2026-11-18 08:45 UTC")
    env.vm.clear_mocks()
    env.vm.warp(iso(E0 + 36 * 60))
    env.vm.sender = env.bob
    env.vm.mock_web(re.escape(f"{SITE}/x/q4-2026.html"), {"status": 200, "body": page1})
    env.vm.mock_web(re.escape(f"{SITE}/x/q3-2026.html"), {"status": 200, "body": "an old page with nothing on it"})
    env.vm.mock_llm(PROMPT, ans(TAR, T_FIGS, period="2026-11-18 08:45 UTC"))
    out = env.c.read(rid, 1)
    assert out["kind"] == "READ", out


@pytest.mark.parametrize("over,needle", [
    (dict(page_urls=["https://reports.example/a.html", "https://reports.example/b.html"]), "one URL per period"),
    (dict(page_urls=["https://reports.example/a.html?q=1"]), "? or #"),
    (dict(page_urls=["https://10.0.0.1/a.html"]), "public address"),
    (dict(page_urls=["https://reports.example"]), "not a bare host"),
    (dict(page_urls=["https://reports.example/a.html"], url_template="https://reports.example/q-{n}.html"), "exactly one"),
])
def test_page_urls_are_checked(env, over, needle):
    spec = {k: v for k, v in live_spec().items() if k != "url_template"}
    spec.update(over)
    env.vm.warp(iso(E0 - 1800))
    env.vm.sender = env.alice
    with pytest.raises(Exception, match=re.escape(needle)):
        env.c.register_report(json.dumps(spec))


def test_v1_digest_is_unchanged_for_a_template_report(env, mod):
    ok, s = mod._spec_problem(json.dumps(live_spec()), E0 - 1800)
    assert ok == "" and "page_urls" not in s and "url_template" in s
