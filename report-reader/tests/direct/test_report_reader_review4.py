"""Regression tests for the weak points found by the fourth independent
review of 18 Nov 2026: each shows the page that used to store a wrong figure
(now refused) and, where there is one, the correct copy that reads; and the
finality mark that can be posted again (remark). Pages are shaped like
Studio's render (one line per row, cells joined by one space). Every
company, page and figure is fictional.
"""

import json

import pytest

from tests.direct.test_report_reader import (  # noqa: F401
    env, mod, iso, register, read, tick, deliver, meth, answer, spec, OPEN0, CLOSE0, END0, ENDS, LAG, WIN, T0,
)
from tests.direct.test_report_reader_review import TAR, live_spec, fig, ans, run, refused  # noqa: F401


def read_ok(r, key, value):
    assert r["kind"] == "READ", r
    assert r["figures"][key] == value, r


def one(key, label, **kw):
    f = {"key": key, "label_hint": label, "labels": [label], "ltm": False, "decimals": 0, "step": 1, "rounding": "down", "sign": "as_printed"}
    f.update(kw)
    return [f]


REV = one("revenue", "Revenue")


def head(heading, cur="euros (EUR)"):
    return (f"{TAR}\nQuarterly results\nResults for the quarter ended 2026-11-18 08:15 UTC. All amounts in {cur}.\n"
            f"{heading}\nQuarter ended 2026-11-18 08:15 UTC Prior quarter\n")


HL = f"{TAR}\nQuarterly highlights\nHighlights for the quarter ended 2026-11-18 08:15 UTC. All amounts in euros (EUR).\n"


# ------------------------------------------- B1: a currency sign in the cells


@pytest.mark.parametrize("cur,curtxt,heading,row,st_units", [
    ("EUR", "euros (EUR)", "All figures in EUR thousands unless stated otherwise.", "Revenue € 15,240 € 14,880", "€"),
    ("EUR", "euros (EUR)", "All figures in EUR thousands unless stated otherwise.", "Revenue EUR 15,240 EUR 14,880", "EUR"),
    ("USD", "US dollars (USD)", "(In thousands, except per share data)", "Revenue $ 15,240 $ 14,880", "$"),
    ("GBP", "pounds sterling (GBP)", "£000", "Revenue £ 15,240 £ 14,880", "£"),
])
def test_b1_a_currency_sign_in_the_cells_is_no_evidence_of_units(env, cur, curtxt, heading, row, st_units):
    page = head(heading, curtxt) + row + "\nOperating costs (9,100) (8,900)\n"
    sp = live_spec(figs=REV, currency=cur)
    refused(run(env, sp, page, ans(TAR, {"revenue": fig("15,240", "Revenue", "units", st_units)}, currency=cur)), "N2_UNITS_MISSING")
    read_ok(run(env, sp, page, ans(TAR, {"revenue": fig("15,240", "Revenue", "thousands", heading)}, currency=cur)), "revenue", "15240000")


def test_b1_a_scale_later_on_the_figures_own_line_refuses_units(env):
    refused(run(env, live_spec(figs=REV), HL + "Revenue: EUR 16.2 (prior year: 14.9) million\n", ans(TAR, {"revenue": fig("16.2", "Revenue", "units", "EUR")})),
            "N2_UNITS_MISSING")


def test_b1_totals_are_never_read_in_whole_units(env):
    # review 5: a heading this code does not know ('(x EUR 1,000)') would make a units copy 1,000x too small
    refused(run(env, live_spec(figs=REV), HL + "Revenue EUR 15,240,000\n", ans(TAR, {"revenue": fig("15,240,000", "Revenue", "units", "EUR")})), "N2_UNITS_MISSING")


# ------------------------------------------ B2: scale words after the value


@pytest.mark.parametrize("line,value,good_scale,good_text,stored", [
    ("Revenue: EUR 16.2 mln", "16.2", "millions", "mln", "16200000"),
    ("Revenue: EUR 1.2 bln", "1.2", "billions", "bln", "1200000000"),
    ("Revenue: EUR 16.2 Mrd", "16.2", "billions", "Mrd", "16200000000"),
    ("Revenue: EUR 16.2 B", "16.2", "billions", "billions", "16200000000"),
])
def test_b2_a_scale_word_after_the_value_decides(env, line, value, good_scale, good_text, stored):
    page = HL + line + "\n"
    refused(run(env, live_spec(figs=REV), page, ans(TAR, {"revenue": fig(value, "Revenue", "units", "EUR")})), "N2_UNITS_MISSING")
    read_ok(run(env, live_spec(figs=REV), page, ans(TAR, {"revenue": fig(value, "Revenue", good_scale, good_text)})), "revenue", stored)


@pytest.mark.parametrize("word", ["crore", "lakh", "cr"])
def test_b2_crore_and_lakh_are_refused_at_every_scale(env, word):
    page = (f"{TAR}\nQuarterly highlights\nHighlights for the quarter ended 2026-11-18 08:15 UTC. All amounts in Indian rupees (INR).\n"
            f"Revenue: INR 1,234 {word}\n")
    sp = live_spec(figs=REV, currency="INR")
    for scale in ("units", "thousands", "millions", "billions"):
        refused(run(env, sp, page, ans(TAR, {"revenue": fig("1,234", "Revenue", scale, scale)}, currency="INR")), "N2_UNITS_MISSING")


# ------------------------------------------- B3: a change after the amount


@pytest.mark.parametrize("line", [
    "Revenue was EUR 1.3 million (9%) higher at EUR 16.2 million",
    "Revenue was EUR 1.3 million, or 9%, higher at EUR 16.2 million",
    "Revenue was EUR 1.3 million or 9% higher at EUR 16.2 million",
    "Revenue was EUR 1.3 million up on the prior year at EUR 16.2 million",
    "Revenue: EUR 1.3 million increase on the prior year, to EUR 16.2 million",
    "Revenue was EUR 1.3 million higher at EUR 16.2 million",
    "Revenue was EUR 1.3 million (or 9 %) above last year",
])
def test_b3_a_change_after_the_amount_is_refused(env, line):
    refused(run(env, live_spec(figs=REV), HL + line + "\n", ans(TAR, {"revenue": fig("EUR 1.3 million", "Revenue", "millions", "million")})), "N2_NOT_ANCHORED")


@pytest.mark.parametrize("line", ["Revenue: EUR 16.2 million, up 9%", "Revenue: EUR 16.2 million, up 9% on the prior year", "Revenue EUR 16.2 million (2025: EUR 14.9 million)",
                                  "Revenue rose 9% to EUR 16.2 million", "Revenue: EUR 16.2 million, an increase of 9%"])
def test_b3_level_lines_still_read(env, line):
    read_ok(run(env, live_spec(figs=REV), HL + line + "\n", ans(TAR, {"revenue": fig("EUR 16.2 million", "Revenue", "millions", "million")})), "revenue", "16200000")


# ----------------------------------------------- B4: pence at any scale


@pytest.mark.parametrize("label,row", [("Interim dividend (pence)", "Interim dividend (pence) 4.5 4.2"), ("Interim dividend (p)", "Interim dividend (p) 4.5 4.2"),
                                       ("Interim dividend", "Interim dividend 4.5 cents 4.2 cents")])
def test_b4_pence_and_cents_are_refused_at_every_scale(env, label, row):
    page = head("£000", "pounds sterling (GBP)") + "Revenue 15,240 14,880\n" + row + "\n"
    figs = one("div", label, decimals=2)
    for scale, st in (("thousands", "£000"), ("units", "(pence)")):
        refused(run(env, live_spec(figs=figs, currency="GBP"), page, ans(TAR, {"div": fig("4.5", label, scale, st)}, currency="GBP")), "N2_UNITS_MISSING")


# ------------------------------------------------- should-fix and nits


def test_s6_in_thousands_of_a_noun_is_prose(env, mod):
    assert mod._heading_scales(mod._norm("We serve customers in thousands of ports."), "EUR") == set()
    assert mod._heading_scales(mod._norm("Amounts in thousands of euros"), "EUR") == {10**3}
    page = HL + "We serve customers in thousands of ports.\nRevenue 15,240\n"
    # no heading names thousands, so a thousands copy is refused; the loose scan still keeps a units copy out (conservative)
    refused(run(env, live_spec(figs=REV), page, ans(TAR, {"revenue": fig("15,240", "Revenue", "units", "EUR")})), "N2_UNITS_MISSING")
    refused(run(env, live_spec(figs=REV), page, ans(TAR, {"revenue": fig("15,240", "Revenue", "thousands", "in thousands")})), "N2_UNITS_MISSING")


def test_n1_a_trailing_minus_refuses_an_unsigned_copy(env):
    page = head("All figures in EUR thousands.") + "Operating profit/(loss) 1,200- 900\n"
    op = one("op", "Operating profit/(loss)")
    refused(run(env, live_spec(figs=op), page, ans(TAR, {"op": fig("1,200", "Operating profit/(loss)")})), "N2_NOT_ANCHORED")


def test_n2_a_month_word_counts_as_a_date_only_next_to_a_number(env, mod):
    end = mod._parse_minute("2026-11-18 08:15")
    assert mod._period_on_page(mod._page_lines("Figures may change: quarter ended 2026-11-18 08:15 UTC\n"), end) is True
    assert mod._period_on_page(mod._page_lines("Quarter ended 17 Feb 2027 and quarter ended 2026-11-18 08:15 UTC\n"), end) is False
    assert mod._period_on_page(mod._page_lines("Quarter ended Feb 17th 2027, quarter ended 2026-11-18 08:15 UTC\n"), end) is False


def test_s5_a_later_period_end_counts_only_on_an_ended_line(env, mod):
    ends = [mod._parse_minute("2027-01-01 00:00"), mod._parse_minute("2027-04-01 00:00")]
    page = "Results for the quarter ended 31 December 2026\nWe expect to complete the disposal by 31 March 2027.\n"
    assert mod._period_on_page(mod._page_lines(page), ends[0], ends[1:]) is True
    page2 = "Results for the quarter ended 31 December 2026\nQuarter ended 31 March 2027 31 December 2026\n"
    assert mod._period_on_page(mod._page_lines(page2), ends[0], ends[1:]) is False


def test_s4_a_glued_code_before_the_digits_refuses(env):
    page = (f"{TAR}\nQuarterly highlights\nHighlights for the quarter ended 2026-11-18 08:15 UTC. All amounts in pounds sterling (GBP).\n"
            "Revenue GBP16.2m\n")
    refused(run(env, live_spec(figs=REV, currency="GBP"), page, ans(TAR, {"revenue": fig("16.2m", "Revenue", "millions", "m")}, currency="GBP")), "N2_NOT_ANCHORED")


# ------------------------------------------------------------ finality: remark


def test_read_can_post_two_messages(env):
    register(env)
    open1 = END0 + 3600 + LAG * 60
    page = __import__("tests.direct.test_report_reader", fromlist=["PAGE"]).PAGE.replace("2026-11-20 10:00 UTC", "2026-11-20 11:00 UTC")
    r = read(env, answer(period_end_on_page="2026-11-20 11:00 UTC"), n=1, at=open1 + 60, page=page)
    assert r["kind"] == "READ", r
    assert sorted(meth(m) for m in env.msgs) == ["confirm_clock", "confirm_read"]


def remark(env, n, at):
    env.vm.warp(iso(at))
    env.vm.sender = env.charlie
    return env.c.remark("1", n)


def test_a_lost_confirm_read_can_be_posted_again(env):
    register(env)
    assert read(env, answer())["kind"] == "READ"
    env.msgs.clear()  # the message is lost
    r = remark(env, 0, OPEN0 + 600)
    assert r["posted"] == "confirm_read" and [meth(m) for m in env.msgs] == ["confirm_read"]
    deliver(env)
    assert env.c.get_reading("1", 0, CLOSE0 + 60)["finalized"] is True
    assert remark(env, 0, OPEN0 + 700)["posted"] == "" and env.msgs == []  # already marked: nothing posted


def test_a_lost_confirm_clock_can_be_posted_again(env):
    register(env)
    last_close = __import__("tests.direct.test_report_reader", fromlist=["ts"]).ts(ENDS[2]) + (LAG + WIN) * 60
    tick(env, at=last_close + 10)
    env.msgs.clear()  # lost
    r = remark(env, 2, last_close + 60)
    assert r["posted"] == "confirm_clock" and env.msgs[0]["calldata"]["args"] == ["1", last_close + 10]
    deliver(env)
    assert env.c.get_reading("1", 2, last_close + 3600)["finalized"] is True


def test_a_period_closed_before_registration_can_be_marked(env):
    register(env, spec(period_ends=[ENDS[0]]), at=CLOSE0 + 60)
    assert env.msgs == []
    remark(env, 0, CLOSE0 + 120)
    deliver(env)
    g = env.c.get_reading("1", 0, CLOSE0 + 3600)
    assert g["status"] == "MISSING" and g["finalized"] is True


def test_remark_refuses_a_period_with_no_final_answer(env):
    register(env)
    with pytest.raises(Exception, match="no final answer yet"):
        remark(env, 0, OPEN0 + 60)
    assert env.msgs == []


def test_in_before_a_singular_scale_word_names_a_heading(env, mod):
    assert mod._heading_scales(mod._norm("Amounts (in thousand)"), "EUR") == {10**3}
    assert mod._heading_scales(mod._norm("Customers in thousand towns"), "EUR") == {10**3}  # a heading word: refuses rather than misreads


def test_b3_a_bracket_after_the_amount_is_skipped(env):
    line = "Revenue was EUR 1.3 million (nine per cent) higher at EUR 16.2 million"
    refused(run(env, live_spec(figs=REV), HL + line + "\n", ans(TAR, {"revenue": fig("EUR 1.3 million", "Revenue", "millions", "million")})), "N2_NOT_ANCHORED")


@pytest.mark.parametrize("heading", ["All figures in EUR mln", "All figures in EUR bln", "Figures in EUR Mrd", "Figures in EUR tsd"])
def test_b2_a_mln_or_bln_heading_keeps_a_units_copy_out(env, heading):
    page = head(heading) + "Revenue 15.2 14.9\n"
    refused(run(env, live_spec(figs=REV), page, ans(TAR, {"revenue": fig("15.2", "Revenue", "units", "EUR")})), "N2_UNITS_MISSING")
