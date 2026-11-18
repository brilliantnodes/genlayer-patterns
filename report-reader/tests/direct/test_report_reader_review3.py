"""Regression tests for the weak points found by the third independent review
of 18 Nov 2026. Each group first shows the page that used to store a wrong
figure (now refused), then that the correct copy of the same page reads.
Pages are shaped like Studio's measured render of mode="text": one line per
table row, cells joined by ONE space, prose lines kept as lines. Every
company, page and figure here is fictional.
"""

import json

import pytest

from tests.direct.test_report_reader import env, mod, iso  # noqa: F401
from tests.direct.test_report_reader_review import (  # noqa: F401
    TAR, E0, SITE, PROMPT, BASE_FIGS, TARNWICK_RENDERED, T_FIGS, live_spec, fig, ans, run, refused,
)


def read_ok(r, key, value):
    assert r["kind"] == "READ", (r.get("reason"), r.get("note"))
    assert r["figures"][key] == value, r


def one(key, label, **kw):
    f = {"key": key, "label_hint": label, "labels": [label], "ltm": False, "decimals": 0, "step": 1, "rounding": "down", "sign": "as_printed"}
    f.update(kw)
    return [f]


def hdr(heading, cur="euros (EUR)"):
    return (f"{TAR}\nQuarterly results\nResults for the quarter ended 2026-11-18 08:15 UTC. All amounts in {cur}.\n"
            f"{heading}\nQuarter ended 2026-11-18 08:15 UTC Prior quarter\n")


HL = f"{TAR}\nQuarterly highlights\nHighlights for the quarter ended 2026-11-18 08:15 UTC. All amounts in euros (EUR).\n"
REV = one("revenue", "Revenue")
OP = [{"key": "op", "label_hint": "Operating profit or loss", "labels": ["Operating profit/(loss)"], "rounding": "down", "sign": "as_printed"}]
LVL = [{**BASE_FIGS[0], "step": 1}]


# ------------------------------------------------ B1: pence and cents per share


@pytest.mark.parametrize("cur,curtxt,row,label,value,st", [
    ("GBP", "pounds sterling (GBP)", "Basic earnings per share (pence) 12.3 11.9", "Basic earnings per share (pence)", "12.3", "(pence)"),
    ("GBP", "pounds sterling (GBP)", "Dividend per share (p) 4.5 4.2", "Dividend per share (p)", "4.5", "(p)"),
    ("USD", "US dollars (USD)", "Diluted earnings per share (US cents) 31.2 28.7", "Diluted earnings per share (US cents)", "31.2", "(US cents)"),
    ("EUR", "euros (EUR)", "Dividend per share (euro cent) 18.0 16.5", "Dividend per share (euro cent)", "18.0", "(euro cent)"),
    ("EUR", "euros (EUR)", "Dividend per share 18.0 cents", "Dividend per share", "18.0", "cents"),
])
def test_b1_a_per_share_figure_in_pence_or_cents_is_refused(env, cur, curtxt, row, label, value, st):
    page = hdr(f"All figures in {cur} thousands, except per share amounts.", curtxt) + "Revenue 15,240 14,880\n" + row + "\n"
    refused(run(env, live_spec(figs=one("dps", label, decimals=2), currency=cur), page, ans(TAR, {"dps": fig(value, label, "units", st)}, currency=cur)),
            "N2_UNITS_MISSING")


def test_b1_a_per_share_figure_in_the_currency_still_reads(env):
    head = hdr("All figures in EUR thousands, except per share amounts.")
    read_ok(run(env, live_spec(figs=one("eps", "Basic EPS (EUR)", decimals=2)), head + "Revenue 15,240 14,880\nBasic EPS (EUR) 0.42 0.40\n",
                ans(TAR, {"eps": fig("0.42", "Basic EPS (EUR)", "units", "(EUR)")})), "eps", "42")


# --------------------------------------------------- B2: scale headings


HEADINGS = ["(in thousands)", "(In thousands, except per share data)", "Thousands", "(thousands)", "Amounts (in thousands)", "in TEUR", "in k€", "in kEUR"]


@pytest.mark.parametrize("heading", HEADINGS)
def test_b2_thousands_headings_read_and_units_are_refused(env, heading):
    page = hdr(heading) + "Revenue 15,240 14,880\n"
    read_ok(run(env, live_spec(figs=REV), page, ans(TAR, {"revenue": fig("15,240", "Revenue", "thousands", heading)})), "revenue", "15240000")
    refused(run(env, live_spec(figs=REV), page, ans(TAR, {"revenue": fig("15,240", "Revenue", "units", "EUR")})), "N2_UNITS_MISSING")


@pytest.mark.parametrize("h,mult", [("(in thousands)", 10**3), ("(In millions, except per share data)", 10**6), ("Thousands", 10**3),
                                    ("in TEUR", 10**3), ("in k€", 10**3), ("MEUR", 10**6), ("EUR Mio", 10**6), ("in thousands", 10**3)])
def test_b2_heading_scan(env, mod, h, mult):
    assert mod._heading_scales(mod._norm(h), "EUR") == {mult}, h


@pytest.mark.parametrize("st,mult", [("TEUR", 10**3), ("kEUR", 10**3), ("MEUR", 10**6), ("Mio", 10**6)])
def test_b2_copied_scale_words(env, mod, st, mult):
    assert mod._scale_mentions(st, "EUR") == {mult}


def test_b2_a_second_table_in_millions_refuses_a_thousands_copy(env):
    page = hdr("All figures in EUR thousands.") + "Revenue 15,240 14,880\nGroup balance sheet (in millions)\nTotal borrowings 48.0 49.5\n"
    tb = one("tb", "Total borrowings")
    refused(run(env, live_spec(figs=tb), page, ans(TAR, {"tb": fig("48.0", "Total borrowings", "thousands", "EUR thousands")})), "N2_UNITS_MISSING")


def test_b2_units_refused_when_a_heading_scale_is_named_loosely(env, mod):
    lines = mod._page_lines("Figures shown in TEUR\nRevenue 15,240")
    assert mod._loose_scales(lines, "EUR") == {10**3}
    assert mod._loose_scales(mod._page_lines("We paid EUR 2.1 million in dividends\nRevenue 15,240"), "EUR") == set()


# ---------------------------------------------- B3: a change after the amount


@pytest.mark.parametrize("line", [
    "Revenue was EUR 1.3 million higher at EUR 16.2 million",
    "Revenue was EUR 1.3 million lower at EUR 14.9 million",
    "Revenue came in EUR 1.3 million above guidance at EUR 16.2 million",
    "Revenue was EUR 1.3 million ahead of the prior year",
])
def test_b3_a_change_after_the_amount_is_refused(env, line):
    refused(run(env, live_spec(figs=LVL), HL + line + "\n", ans(TAR, {"revenue": fig("EUR 1.3 million", "Revenue", "millions", "million")})), "N2_NOT_ANCHORED")


@pytest.mark.parametrize("line", ["Revenue rose 9% to EUR 16.2 million", "Revenue: EUR 16.2 million, up 9%", "Revenue EUR 16.2 million (2025: EUR 14.9 million)"])
def test_b3_level_lines_still_read(env, line):
    read_ok(run(env, live_spec(figs=LVL), HL + line + "\n", ans(TAR, {"revenue": fig("EUR 16.2 million", "Revenue", "millions", "million")})), "revenue", "16200000")


# --------------------------------------------------- B4: EPS and /share labels


@pytest.mark.parametrize("label,value", [("Basic EPS", "0.42"), ("Diluted EPS", "0.41"), ("NAV/share", "12.34"), ("NAV/unit", "12.34")])
def test_b4_eps_and_slash_share_labels_never_take_the_heading_scale(env, label, value):
    page = hdr("All figures in EUR thousands, except per share amounts.") + f"Revenue 15,240 14,880\n{label} {value} 0.40\n"
    refused(run(env, live_spec(figs=one("x", label, decimals=2)), page, ans(TAR, {"x": fig(value, label, "thousands", "EUR thousands")})), "N2_UNITS_MISSING")


# ------------------------------------------------ B5: signs and empty cells


@pytest.mark.parametrize("cell", ["‐1,200", "‑1,200", "﹘1,200", "⸺1,200", "△1,200", "▲1,200", "( 1,200 )", "~1,200"])
def test_b5_a_sign_mark_the_copy_dropped_refuses(env, cell):
    page = hdr("All figures in EUR thousands.") + f"Revenue 15,240 14,880\nOperating profit/(loss) {cell} 900\n"
    refused(run(env, live_spec(figs=OP), page, ans(TAR, {"op": fig("1,200", "Operating profit/(loss)")})), "N2_NOT_ANCHORED")


@pytest.mark.parametrize("cell", ["( 1,200 )", "‑1,200", "‐1,200"])
def test_b5_the_copy_with_its_sign_reads(env, cell):
    page = hdr("All figures in EUR thousands.") + f"Revenue 15,240 14,880\nOperating profit/(loss) {cell} 900\n"
    read_ok(run(env, live_spec(figs=OP), page, ans(TAR, {"op": fig(cell, "Operating profit/(loss)")})), "op", "-1200000")


@pytest.mark.parametrize("row", ["Operating profit/(loss) ‑ (1,200)", "Operating profit/(loss) € – € (1,200)", "Operating profit/(loss) … (1,200)",
                                 "Operating profit/(loss) ... (1,200)", "Operating profit/(loss) * (1,200)", "Operating profit/(loss) . (1,200)"])
def test_b5_a_value_after_an_empty_cell_mark_is_refused(env, row):
    page = hdr("All figures in EUR thousands.") + "Revenue 15,240 14,880\n" + row + "\n"
    refused(run(env, live_spec(figs=OP), page, ans(TAR, {"op": fig("(1,200)", "Operating profit/(loss)")})), "N2_NOT_ANCHORED")


def test_b5_a_footnote_star_on_the_label_still_reads(env):
    read_ok(run(env, live_spec(figs=REV), hdr("All figures in EUR thousands.") + "Revenue* 15,240 14,880\n", ans(TAR, {"revenue": fig("15,240", "Revenue")})),
            "revenue", "15240000")


# ------------------------------------------------- B6: the period on the page


def two_period_spec():
    sp = live_spec()
    sp["period_ends"] = ["2026-11-18 08:15", "2027-02-17 08:15"]
    return sp


@pytest.mark.parametrize("page", [
    f"{TAR}\nQuarterly results\nAll figures in EUR thousands.\nQuarter ended 2027-02-17 08:15 UTC Quarter ended 2026-11-18 08:15 UTC\nRevenue 16,010 15,240\n",
    f"{TAR}\nResults for the quarter ended 2027-02-17 08:15 UTC. Revenue grew 5% compared with the quarter ended 2026-11-18 08:15 UTC.\n"
    "All figures in EUR thousands.\nRevenue 16,010 15,240\n",
])
def test_b6_next_quarters_page_is_refused(env, mod, page):
    lines = mod._page_lines(page)
    assert not mod._period_on_page(lines, E0)  # this period only as the second column or after 'compared'
    assert not mod._period_on_page(lines + mod._page_lines("Results for the quarter ended 2026-11-18 08:15 UTC."), E0, [E0 + 91 * 86400])  # a later end printed


@pytest.mark.parametrize("zone", ["UTC+04:00", "UTC-5", "GMT+4", "(CET)", "ET", "local time", "", "CET", "0 UTC", "UTCX"])
def test_b6_a_period_end_in_another_zone_or_with_an_offset_is_refused(env, zone):
    page = TARNWICK_RENDERED.replace("2026-11-18 08:15 UTC", f"2026-11-18 08:15 {zone}".rstrip())
    refused(run(env, live_spec(), page, ans(TAR, T_FIGS, period="2026-11-18 08:15")), "N2_WRONG_PERIOD")


@pytest.mark.parametrize("text", ["ended 2026-11-18 08:15 UTC.", "ended 2026-11-18 08:15 GMT", "ended 2026-11-18T08:15Z", "ended 2026-11-18 08:15:00 UTC",
                                  "ended 2026-11-18 08:15 (UTC)", "ended 2026-11-18 08:15 UTC - see note 2"])
def test_b6_utc_forms_read(env, mod, text):
    assert mod._period_on_page(mod._page_lines(text), E0)


def test_b6_the_page_is_always_cut_at_a_line_break(env, mod):
    head = f"{TAR}\nResults for the quarter ended 2026-11-18 08:15 UTC. All figures in EUR thousands unless stated otherwise.\n"
    pre = (head + "Highlights: " + "strong trading; " * 2000)[: mod.PAGE_CHARS - len("; Revenue EUR 16.2 ")]
    body = pre + "; Revenue EUR 16.2 million; more text " * 3
    cut = mod._clean_page(body)
    assert "Revenue EUR 16.2" not in cut and cut.endswith("unless stated otherwise.")  # the last whole line, untouched
    refused(run(env, live_spec(figs=REV), body, ans(TAR, {"revenue": fig("EUR 16.2", "Revenue", "thousands", "EUR thousands")})), "N2_NOT_ANCHORED")


# --------------------------------------------------------------- should-fix


def test_s1_the_scale_is_read_where_the_value_was_anchored(env):
    page = f"{TAR}\nHighlights for the quarter ended 2026-11-18 08:15 UTC. Tables in EUR thousands.\nRevenue rose 16.2% to EUR 16.2 million\n"
    refused(run(env, live_spec(figs=REV), page, ans(TAR, {"revenue": fig("16.2", "Revenue", "thousands", "EUR thousands")})), "N2_UNITS_MISSING")
    read_ok(run(env, live_spec(figs=REV), page, ans(TAR, {"revenue": fig("16.2", "Revenue", "millions", "million")})), "revenue", "16200000")


def test_s2_the_ltm_word_must_come_before_the_value(env):
    figs = one("le", "EBITDA", ltm=True)
    refused(run(env, live_spec(figs=figs), HL + "EBITDA EUR 1.2 million (LTM EUR 4.4 million)\n",
                ans(TAR, {"le": fig("EUR 1.2 million", "EBITDA", "millions", "million", ltm="yes")})), "N2_NOT_LTM")
    figs = one("le", "LTM EBITDA", ltm=True)
    read_ok(run(env, live_spec(figs=figs), HL + "LTM EBITDA EUR 4.4 million\n",
                ans(TAR, {"le": fig("EUR 4.4 million", "LTM EBITDA", "millions", "million", ltm="yes")})), "le", "4400000")


@pytest.mark.parametrize("label,value", [("Revenue¹", "15,240"), ("Revenue", "15,240¹"), ("Revenue¹", "15,240¹")])
def test_s3_a_faithful_copy_with_a_footnote_mark_reads(env, label, value):
    page = hdr("All figures in EUR thousands.") + "Revenue¹ 15,240¹ 14,880\n"
    read_ok(run(env, live_spec(figs=REV), page, ans(TAR, {"revenue": fig(value, label)})), "revenue", "15240000")


@pytest.mark.parametrize("line,millions", [("Over a million customers now pay in euros.", False),
                                           ("We paid EUR 2.1 million in dividends to thousands of shareholders.", True)])
def test_s4_a_prose_line_naming_the_currency_and_a_scale_word_no_longer_refuses(env, line, millions):
    m = {k: {**v, "scale": "millions", "scale_text": "EUR millions"} for k, v in T_FIGS.items()}
    base, figs = (TARNWICK_RENDERED.replace("EUR thousands", "EUR millions"), m) if millions else (TARNWICK_RENDERED, T_FIGS)
    assert run(env, live_spec(), base.replace("The board approved", line + "\nThe board approved"), ans(TAR, figs))["kind"] == "READ"


def test_s5_duplicate_page_urls_are_refused(env, mod):
    sp = {k: v for k, v in live_spec().items() if k != "url_template"}
    sp["period_ends"] = ["2026-11-18 08:15", "2027-02-17 08:15"]
    sp["page_urls"] = [f"{SITE}/latest.html", f"{SITE}/latest.html"]
    assert "own page" in mod._spec_problem(json.dumps(sp), E0 - 1800)[0]
    sp["page_urls"] = [f"{SITE}/q-1.html", f"{SITE}/q-2.html"]
    assert mod._spec_problem(json.dumps(sp), E0 - 1800)[0] == ""


@pytest.mark.parametrize("text", ["Priority results for the quarter ended 2026-11-18 08:15 UTC.", "Apriori plc results for the quarter ended 2026-11-18 08:15 UTC."])
def test_s7_prior_words_match_whole_words_only(env, mod, text):
    assert mod._period_on_page(mod._page_lines(text), E0)


@pytest.mark.parametrize("text", ["Prior quarter ended 2026-11-18 08:15 UTC", "Compared with the quarter ended 2026-11-18 08:15 UTC",
                                  "Revenue vs 2026-11-18 08:15 UTC", "Previous: 2026-11-18 08:15 UTC"])
def test_s6_prior_words_refuse(env, mod, text):
    assert not mod._period_on_page(mod._page_lines(text), E0)


@pytest.mark.parametrize("text", ["Year ended 31 Dec 2026", "Year ended 31.12.2026", "Year ended 31st December 2026", "Year ended December 31st, 2026",
                                  "Year ended 31/12/2026", "Year ended Dec. 31, 2026", "Year ended 31 December 2026"])
def test_s9_common_date_forms_read(env, mod, text):
    end = 1798761600  # 2027-01-01 00:00 UTC: the period that ends with 31 December 2026
    assert mod._period_on_page(mod._page_lines(text), end)


def test_s9_ambiguous_numeric_dates_are_not_read(env, mod):
    end = 1772668800  # 2026-03-05 00:00 UTC: last day 4 March
    for t in ("Period ended 04/03/2026", "Period ended 4/03/2026", "Period ended 4.3.2026"):
        assert not mod._period_on_page(mod._page_lines(t), end), t
    assert mod._period_on_page(mod._page_lines("Period ended 4 March 2026"), end)


# ----------------------------------------------- second-review fixes still hold


@pytest.mark.parametrize("line,millions", [("The results call starts at 10:00 a.m. UTC.", False), ("Our M&A pipeline remains strong.", False),
                                           ("Employees may join the 401(k) plan.", True), ("We now serve thousands of customers.", True)])
def test_ok_ordinary_lines_do_not_refuse(env, line, millions):
    m = {k: {**v, "scale": "millions", "scale_text": "EUR millions"} for k, v in T_FIGS.items()}
    base, figs = (TARNWICK_RENDERED.replace("EUR thousands", "EUR millions"), m) if millions else (TARNWICK_RENDERED, T_FIGS)
    assert run(env, live_spec(), base.replace("The board approved", line + "\nThe board approved"), ans(TAR, figs))["kind"] == "READ"


def test_ok_sign_before_currency(env):
    page = hdr("All figures in EUR thousands.") + "Revenue 15,240 14,880\nOperating profit/(loss) -€1,200 900\n"
    refused(run(env, live_spec(figs=OP), page, ans(TAR, {"op": fig("1,200", "Operating profit/(loss)")})), "N2_NOT_ANCHORED")
    read_ok(run(env, live_spec(figs=OP), page, ans(TAR, {"op": fig("-€1,200", "Operating profit/(loss)")})), "op", "-1200000")


def test_b6_a_zone_glued_to_the_minute_is_refused(env, mod):
    assert not mod._period_on_page(mod._page_lines("ended 2026-11-18 08:15utc"), E0)  # the zone must stand as its own word


def test_b2_in_before_a_scale_word_names_a_heading(env, mod):
    assert mod._heading_scales(mod._norm("Amounts in millions of U.S. dollars"), "USD") == {10**6}
    assert mod._heading_scales(mod._norm("Millions of shares were bought back."), "USD") == set()


def test_b2_a_loose_scale_anywhere_refuses_units(env):
    page = hdr("Amounts shown in euros.") + "Millions of shares were bought back.\nRevenue 15,240,000 14,880,000\n"
    refused(run(env, live_spec(figs=REV), page, ans(TAR, {"revenue": fig("15,240,000", "Revenue", "units", "euros")})), "N2_UNITS_MISSING")
    page = hdr("Amounts shown in euros.") + "Revenue 15,240,000 14,880,000\n"
    refused(run(env, live_spec(figs=REV), page, ans(TAR, {"revenue": fig("15,240,000", "Revenue", "units", "euros")})), "N2_UNITS_MISSING")  # totals: never units