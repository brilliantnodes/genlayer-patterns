"""Regression tests for the weak points found by the fifth independent
review of 18 Nov 2026. The rule changed rather than the list of layouts:
totals are never read in whole units, so a scale heading this code does not
know can only make a page read nothing. Each group shows the page that used
to store a wrong figure (now refused) and, where there is one, the correct
copy that reads. Pages are shaped like Studio's render (one line per row,
cells joined by one space). Every company, page and figure is fictional.
"""

import pytest

from tests.direct.test_report_reader import (  # noqa: F401
    env, mod, iso, register, read, tick, deliver, meth, answer, spec, OPEN0, CLOSE0, END0, ENDS, LAG, WIN, ts,
)
from tests.direct.test_report_reader_review import TAR, live_spec, fig, ans, run, refused  # noqa: F401


def read_ok(r, key, value):
    assert r["kind"] == "READ", (r.get("reason"), r)
    assert r["figures"][key] == value, r


def one(key, label, **kw):
    f = {"key": key, "label_hint": label, "labels": [label], "ltm": False, "decimals": 0, "step": 1, "rounding": "down", "sign": "as_printed"}
    f.update(kw)
    return [f]


REV = one("revenue", "Revenue")
END = "Results for the quarter ended 2026-11-18 08:15 UTC."


def page(cur_words, *lines):
    return f"{TAR}\nQuarterly results\n{END} All amounts in {cur_words}.\n" + "\n".join(lines) + "\n"


# ------------------------------------------- B1: totals never in whole units

HEADINGS = [
    ("EUR", "euros (EUR)", "(x EUR 1,000)", "EUR", "thousands", "15240000"),
    ("EUR", "euros (EUR)", "Amounts in € x 1,000", "€", "thousands", "15240000"),
    ("EUR", "euros (EUR)", "Bedragen in 1.000 EUR", "EUR", "thousands", "15240000"),
    ("NOK", "Norwegian kroner (NOK)", "Amounts in NOK 1000", "NOK", "thousands", "15240000"),
    ("NOK", "Norwegian kroner (NOK)", "NOK 1000", "NOK", "thousands", None),  # a bare amount-like heading is not recognised: nothing reads
    ("USD", "US dollars (USD)", "(000 omitted)", "USD", "thousands", "15240000"),
    ("EUR", "euros (EUR)", "All figures in M€", "€", "millions", "15240000000"),
    ("EUR", "euros (EUR)", "in T€", "€", "thousands", "15240000"),
    ("EUR", "euros (EUR)", "EUR (m)", "EUR", "millions", "15240000000"),
    ("NOK", "Norwegian kroner (NOK)", "Amounts in NOK mill.", "NOK", "millions", "15240000000"),
]


@pytest.mark.parametrize("cur,curw,heading,units_st,good_scale,good", HEADINGS)
def test_b1_a_units_copy_of_a_total_is_refused_under_any_heading(env, cur, curw, heading, units_st, good_scale, good):
    p = page(curw, heading, "Quarter ended 2026-11-18 08:15 UTC Prior quarter", "Revenue 15,240 14,880", "Operating costs (9,100) (8,900)")
    sp = live_spec(figs=REV, currency=cur)
    refused(run(env, sp, p, ans(TAR, {"revenue": fig("15,240", "Revenue", "units", units_st)}, currency=cur)), "N2_UNITS_MISSING")
    r = run(env, sp, p, ans(TAR, {"revenue": fig("15,240", "Revenue", good_scale, heading)}, currency=cur))
    if good is None:
        refused(r, "N2_UNITS_MISSING")
    else:
        read_ok(r, "revenue", good)


def test_b1_a_second_table_heading_in_another_scale_refuses(env):
    p = page("euros (EUR)", "All figures in EUR thousands.", "Revenue 15,240 14,880", "Balance sheet (x EUR 1,000,000)", "Total borrowings 48.0 49.5")
    tb = one("tb", "Total borrowings")
    refused(run(env, live_spec(figs=tb), p, ans(TAR, {"tb": fig("48.0", "Total borrowings", "thousands", "EUR thousands")})), "N2_UNITS_MISSING")


@pytest.mark.parametrize("line", ["Revenue EUR 2,000", "Fee of EUR 1,000 paid"])
def test_b1_a_bare_currency_amount_names_no_heading(env, mod, line):
    assert mod._heading_scales(mod._norm(line), "EUR") == set()


# --------------------------------------------- B2: more words after the value


@pytest.mark.parametrize("cur,curw,line,value,good_scale,good", [
    ("JPY", "Japanese yen (JPY)", "Revenue: JPY 45.1 trillion", "45.1", None, None),
    ("JPY", "Japanese yen (JPY)", "Revenue: JPY 45.1 tn", "45.1", None, None),
    ("EUR", "euros (EUR)", "Revenue: EUR 16.2 mill.", "16.2", "millions", "16200000"),
    ("USD", "US dollars (USD)", "Revenue: USD 16.2 mil", "16.2", None, None),  # 'mil': million or (Spanish) thousand: refused
])
def test_b2_trillions_refuse_and_mill_reads_as_millions(env, cur, curw, line, value, good_scale, good):
    p = page(curw, line)
    sp = live_spec(figs=REV, currency=cur)
    for scale in ("units", "thousands", "millions", "billions"):
        r = run(env, sp, p, ans(TAR, {"revenue": fig(value, "Revenue", scale, scale)}, currency=cur))
        if scale == good_scale:
            read_ok(r, "revenue", good)
        else:
            refused(r, "N2_UNITS_MISSING")


# ----------------------------------------------- B3: changes after the amount


@pytest.mark.parametrize("cur,curw,line,value", [
    ("USD", "US dollars (USD)", "Revenue was USD 1.3 million, or 9 percent, higher than in the prior-year quarter", "USD 1.3 million"),
    ("EUR", "euros (EUR)", "Revenue was EUR 1.3 million up year-on-year at EUR 16.2 million", "EUR 1.3 million"),
    ("EUR", "euros (EUR)", "Revenue was EUR 1.3 million greater than in the prior year", "EUR 1.3 million"),
    ("EUR", "euros (EUR)", "Revenue: EUR 1.3 million year-on-year increase, to EUR 16.2 million", "EUR 1.3 million"),
    ("EUR", "euros (EUR)", "Revenue was EUR 1.3 million, or 9 per cent, higher at EUR 16.2 million", "EUR 1.3 million"),
    ("EUR", "euros (EUR)", "Revenue was EUR 1.3 million (9 pct) larger than a year ago", "EUR 1.3 million"),
])
def test_b3_a_change_after_the_amount_is_refused(env, cur, curw, line, value):
    p = page(curw, line)
    refused(run(env, live_spec(figs=REV, currency=cur), p, ans(TAR, {"revenue": fig(value, "Revenue", "millions", "million")}, currency=cur)), "N2_NOT_ANCHORED")


def test_b3_per_cent_is_read_as_a_percentage(env, mod):
    rest = mod._norm("Revenue was EUR 1.3 million, or 9 per cent, higher at EUR 16.2 million").split("1.3 million", 1)[1]
    assert mod._change_after(rest) is True


# ------------------------------------------------ B4: pence off the line, ¢


def test_b4_pence_in_the_column_heads_above_refuses(env):
    p = page("pounds sterling (GBP)", "£000", "Quarter ended 2026-11-18 08:15 UTC Prior quarter", "Revenue 15,240 14,880", "pence pence", "Interim dividend 4.5 4.2")
    figs = one("div", "Interim dividend", decimals=2)
    for scale, st in (("thousands", "£000"), ("units", "GBP")):
        refused(run(env, live_spec(figs=figs, currency="GBP"), p, ans(TAR, {"div": fig("4.5", "Interim dividend", scale, st)}, currency="GBP")), "N2_UNITS_MISSING")


@pytest.mark.parametrize("label,st", [("Quarterly dividend per share", "¢"), ("Quarterly dividend", "USD")])
def test_b4_the_cent_sign_refuses(env, label, st):
    p = page("US dollars (USD)", f"{label} 4.5¢")
    figs = one("dps", label, decimals=2)
    r = run(env, live_spec(figs=figs, currency="USD"), p, ans(TAR, {"dps": fig("4.5", label, "units", st)}, currency="USD"))
    assert r["kind"] == "NO_READING", r


# ------------------------------------------------- F1-F3: no false refusals


@pytest.mark.parametrize("cur,curw,heading", [
    ("CAD", "Canadian dollars (CAD)", "(in thousands of Canadian dollars, except per share amounts)"),
    ("CHF", "Swiss francs (CHF)", "(in thousands of Swiss francs)"),
    ("AUD", "Australian dollars (AUD)", "(in thousands of Australian dollars)"),
    ("SEK", "Swedish kronor (SEK)", "(in millions of Swedish kronor)"),
])
def test_f1_in_thousands_of_a_named_currency_is_a_heading(env, mod, cur, curw, heading):
    assert mod._heading_scales(mod._norm(heading), cur) != set()
    mult = "millions" if "millions" in heading else "thousands"
    p = page(curw, heading, "Quarter ended 2026-11-18 08:15 UTC Prior quarter", "Revenue 15,240 14,880")
    read_ok(run(env, live_spec(figs=REV, currency=cur), p, ans(TAR, {"revenue": fig("15,240", "Revenue", mult, heading)}, currency=cur)),
            "revenue", "15240000" if mult == "thousands" else "15240000000")


@pytest.mark.parametrize("line", ["Revenue of £16.2 million, up 9 per cent", "Revenue £16.2 million (2025: £14.9 million), an increase of 9 per cent",
                                  "Revenue of £16.2 million, up 9%"])
def test_f2_per_cent_is_not_pence(env, line):
    p = page("pounds sterling (GBP)", line)
    read_ok(run(env, live_spec(figs=REV, currency="GBP"), p, ans(TAR, {"revenue": fig("£16.2 million", "Revenue", "millions", "million")}, currency="GBP")),
            "revenue", "16200000")


@pytest.mark.parametrize("cur,curw,line,value", [
    ("USD", "US dollars (USD)", "Revenue was USD 16.2 million, up from USD 14.9 million in the prior-year quarter", "USD 16.2 million"),
    ("EUR", "euros (EUR)", "Revenue: EUR 16.2 million, down from EUR 17.0 million", "EUR 16.2 million"),
    ("GBP", "pounds sterling (GBP)", "Revenue £16.2 million, up on last year's £14.9 million", "£16.2 million"),
    ("EUR", "euros (EUR)", "Revenue of EUR 16.2 million, an increase from EUR 14.9 million", "EUR 16.2 million"),
])
def test_f3_a_level_up_from_a_prior_amount_reads(env, cur, curw, line, value):
    p = page(curw, line)
    read_ok(run(env, live_spec(figs=REV, currency=cur), p, ans(TAR, {"revenue": fig(value, "Revenue", "millions", "million")}, currency=cur)),
            "revenue", "16200000")


# ---------------------------------------------- S5: '... months to' pages


def test_s5_next_period_page_written_months_to_is_refused(env, mod):
    ends = [mod._parse_minute("2027-01-01 00:00"), mod._parse_minute("2027-07-01 00:00")]
    p = ("Interim results for the six months to 30 June 2027\n"
         "Net debt has fallen by EUR 1.5 million since 31 December 2026.\n"
         "30 June 2027 30 June 2026 31 December 2026\n")
    assert mod._period_on_page(mod._page_lines(p), ends[0], ends[1:]) is False


# --------------------------------------------------------- remark, more


def remark(env, n, at, who=None):
    env.vm.warp(iso(at))
    env.vm.sender = who or env.charlie
    return env.c.remark("1", n)


def test_remark_before_finality_posts_again_and_the_marks_agree(env):
    register(env)
    assert read(env, answer())["kind"] == "READ"
    for k in range(3):
        assert remark(env, 0, OPEN0 + 300 + k)["posted"] == "confirm_read"
    assert [meth(m) for m in env.msgs] == ["confirm_read"] * 4
    assert [r["ok"] for _, r in deliver(env)] == [True] * 4
    assert env.c.get_reading("1", 0, CLOSE0 + 60)["finalized"] is True


def test_remark_moves_no_clock_and_cannot_make_missing(env):
    register(env)
    with pytest.raises(Exception, match="no final answer yet"):
        remark(env, 0, CLOSE0 + 600)
    assert env.c.get_reading("1", 0, CLOSE0 + 600)["status"] == "CLOSING"


def test_a_lost_mark_is_healed_by_a_later_confirm_clock(env):
    register(env)
    tick(env, at=CLOSE0 + 10)
    env.msgs.clear()
    last_close = ts(ENDS[2]) + (LAG + WIN) * 60
    tick(env, at=last_close + 10)
    deliver(env)
    assert env.c.get_reading("1", 0, last_close + 60)["finalized"] is True
    assert remark(env, 0, last_close + 60)["posted"] == ""


def test_a_scale_word_in_prose_elsewhere_refuses_a_scaled_copy(env):
    p = page("euros (EUR)", "All figures in EUR thousands.", "Revenue 15,240 14,880", "Group balance sheet (million)", "Total borrowings 48.0 49.5")
    tb = one("tb", "Total borrowings")
    refused(run(env, live_spec(figs=tb), p, ans(TAR, {"tb": fig("48.0", "Total borrowings", "thousands", "EUR thousands")})), "N2_UNITS_MISSING")


@pytest.mark.parametrize("line", ["Over a million customers now pay in euros.", "We now serve thousands of customers.", "One million passengers flew with us."])
def test_prose_scale_words_do_not_refuse_a_scaled_copy(env, line):
    p = page("euros (EUR)", "All figures in EUR thousands.", line, "Revenue 15,240 14,880")
    read_ok(run(env, live_spec(figs=REV), p, ans(TAR, {"revenue": fig("15,240", "Revenue", "thousands", "EUR thousands")})), "revenue", "15240000")


@pytest.mark.parametrize("h,mult", [("(x EUR 1,000)", 10**3), ("in € × 1.000", 10**3), ("in 1 000 EUR", 10**3), ("(in EUR 1,000,000)", 10**6),
                                    ("x 1.000.000", 10**6), ("(000 omitted)", 10**3), ("(000s omitted)", 10**3)])
def test_multiplier_headings(env, mod, h, mult):
    assert mod._heading_scales(mod._norm(h), "EUR") == {mult}


def test_a_per_share_copy_whose_words_name_a_scale_is_refused(env):
    p = page("euros (EUR)", "Basic EPS (k) 0.42 0.40")
    figs = one("eps", "Basic EPS", decimals=2)
    refused(run(env, live_spec(figs=figs), p, ans(TAR, {"eps": fig("0.42", "Basic EPS", "units", "k")})), "N2_UNITS_MISSING")
