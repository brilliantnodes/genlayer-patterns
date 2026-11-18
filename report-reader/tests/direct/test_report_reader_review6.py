"""Regression tests for the weak points found by the sixth independent
review of 18 Nov 2026. A per-share figure is decided first and read only in
units, with the copied words exactly the report's currency printed on its
line, so a sub-unit spelling this code does not list can only refuse. Each
group shows the page that used to store a wrong figure (now refused) and,
where there is one, the correct copy that reads. Pages are shaped like
Studio's render (one line per row, cells joined by one space). Every
company, page and figure is fictional.
"""

import pytest

from tests.direct.test_report_reader import env, mod  # noqa: F401
from tests.direct.test_report_reader_review import TAR, live_spec, fig, ans, run, refused  # noqa: F401


def read_ok(r, key, value):
    assert r["kind"] == "READ", (r.get("reason"), r)
    assert r["figures"][key] == value, r


def one(key, label, **kw):
    f = {"key": key, "label_hint": "".join(c for c in label if c.isalnum() or c in " ,.()-/'&%:"), "labels": [label], "ltm": False, "decimals": 0,
         "step": 1, "rounding": "down", "sign": "as_printed"}
    f.update(kw)
    return [f]


REV = one("revenue", "Revenue")
END = "Results for the quarter ended 2026-11-18 08:15 UTC."


def page(cur_words, *lines):
    return f"{TAR}\nQuarterly results\n{END} All amounts in {cur_words}.\n" + "\n".join(lines) + "\n"


# ------------------------------------------- B1: sub-units this code does not list


@pytest.mark.parametrize("cur,curw,label,line,st", [
    ("AUD", "Australian dollars (AUD)", "Basic earnings per share", "Basic earnings per share (c) 45.2 41.0", "(c)"),
    ("EUR", "euros (EUR)", "Basic earnings per share (€c)", "Basic earnings per share (€c) 45.2 41.0", "€c"),
    ("AUD", "Australian dollars (AUD)", "Dividend per share (cps)", "Dividend per share (cps) 45.0 41.0", "cps"),
    ("KWD", "Kuwaiti dinars (KWD)", "Basic and diluted earnings per share (fils)", "Basic and diluted earnings per share (fils) 25.3 22.1", "fils"),
])
def test_b1_a_per_share_figure_in_an_unlisted_sub_unit_is_refused(env, cur, curw, label, line, st):
    p = page(curw, "Quarter ended 2026-11-18 08:15 UTC Prior quarter", line)
    figs = one("eps", label, decimals=2)
    value = line.split(") ")[1].split(" ")[0]
    refused(run(env, live_spec(figs=figs, currency=cur), p, ans(TAR, {"eps": fig(value, label, "units", st)}, currency=cur)), "N2_UNITS_MISSING")


@pytest.mark.parametrize("cur,curw,line,st", [("EUR", "euros (EUR)", "Basic earnings per share (EUR) 0.45 0.40", "(EUR)"),
                                              ("EUR", "euros (EUR)", "Basic earnings per share € 0.45 € 0.40", "€"),
                                              ("USD", "US dollars (USD)", "Diluted EPS USD 0.45 USD 0.40", "USD")])
def test_b1_a_per_share_figure_in_the_currency_reads(env, cur, curw, line, st):
    label = "Diluted EPS" if "EPS" in line else "Basic earnings per share"
    p = page(curw, "Quarter ended 2026-11-18 08:15 UTC Prior quarter", line)
    read_ok(run(env, live_spec(figs=one("eps", label, decimals=2), currency=cur), p, ans(TAR, {"eps": fig("0.45", label, "units", st)}, currency=cur)), "eps", "45")


# --------------------------------------------- B2: 'as per' is not per share


@pytest.mark.parametrize("label", ["Net debt as per covenant definition", "EBITDA as per facility agreement"])
def test_b2_an_as_per_label_is_a_total(env, mod, label):
    assert mod._per_share_label(mod._norm_label(label)) is False
    p = page("euros (EUR)", "All figures in EUR thousands.", "Quarter ended 2026-11-18 08:15 UTC Prior quarter", f"{label} EUR 48,000 EUR 49,500")
    figs = one("nd", label)
    refused(run(env, live_spec(figs=figs), p, ans(TAR, {"nd": fig("48,000", label, "units", "EUR")})), "N2_UNITS_MISSING")
    read_ok(run(env, live_spec(figs=figs), p, ans(TAR, {"nd": fig("48,000", label, "thousands", "EUR thousands")})), "nd", "48000000")


@pytest.mark.parametrize("label,yes", [("Earnings per share", True), ("Earnings per ordinary share", True), ("Dividend per unit", True), ("Basic EPS", True),
                                       ("DPS (EUR)", True), ("NAV/share", True), ("Revenue per employee", False), ("Net debt as per covenant", False)])
def test_b2_per_share_labels(env, mod, label, yes):
    assert mod._per_share_label(mod._norm_label(label)) is yes


# ------------------------------------- B3: a per-share figure never takes a scale


def test_b3_a_per_share_figure_ignores_a_scale_on_its_line(env):
    p = page("euros (EUR)", "Earnings per share (EUR) 0.45 0.40 Dividends paid (EUR m) 12.0 11.0")
    figs = one("eps", "Earnings per share", decimals=2)
    refused(run(env, live_spec(figs=figs), p, ans(TAR, {"eps": fig("0.45", "Earnings per share", "millions", "EUR m")})), "N2_UNITS_MISSING")
    read_ok(run(env, live_spec(figs=figs), p, ans(TAR, {"eps": fig("0.45", "Earnings per share", "units", "EUR")})), "eps", "45")


# --------------------------------------------------- B4: more heading forms


@pytest.mark.parametrize("cur,form,mult", [("GBP", "£'m", 10**6), ("EUR", "€'m", 10**6), ("EUR", "EUR'm", 10**6), ("EUR", "m EUR", 10**6), ("EUR", "k EUR", 10**3),
                                           ("GBP", "£ 000", 10**3), ("USD", "US$ 000", 10**3), ("EUR", "in Tausend EUR", 10**3), ("EUR", "en milliers d'euros", 10**3),
                                           ("EUR", "(in Tsd. EUR)", 10**3), ("EUR", "Tsd. EUR", 10**3)])
def test_b4_heading_forms(env, mod, cur, form, mult):
    lines = mod._page_lines(f"Balance sheet {form}\nTotal borrowings 48.0 49.5\n")
    assert mod._page_scales(lines, cur) == {mult}


@pytest.mark.parametrize("cur,curw,known,unknown", [("GBP", "pounds sterling (GBP)", "£'000", "£'m"), ("EUR", "euros (EUR)", "EUR thousands", "m EUR"),
                                                    ("EUR", "euros (EUR)", "EUR million", "k EUR")])
def test_b4_a_page_with_two_scales_refuses(env, cur, curw, known, unknown):
    p = page(curw, f"Income statement ({known})", "Revenue 15,240 14,880", f"Balance sheet ({unknown})", "Total borrowings 48.0 49.5")
    tb = one("tb", "Total borrowings")
    for scale, st in (("thousands", known), ("millions", known), ("thousands", unknown), ("millions", unknown)):
        refused(run(env, live_spec(figs=tb, currency=cur), p, ans(TAR, {"tb": fig("48.0", "Total borrowings", scale, st)}, currency=cur)), "N2_UNITS_MISSING")


# ----------------------------------------------- B5: changes after the amount


@pytest.mark.parametrize("line", [
    "Revenue: EUR 1.3 million year-over-year increase, to EUR 16.2 million",
    "Revenue: EUR 1.3 million quarter-on-quarter increase, to EUR 16.2 million",
    "Revenue: EUR 1.3 million like-for-like increase",
    "Revenue was EUR 1.3 million up on 2025 at EUR 16.2 million",
    "Revenue: EUR 1.3 million growth over 2025",
    "Revenue: EUR 1.3 million increase compared with 2025",
    "Revenue: EUR 1.3 million increase on last year's EUR 14.9 million",
    "Revenue: EUR 1.3 million increase from EUR 14.9 million",
    "Revenue: EUR 1.3 million year-on-year increase, to EUR 16.2 million",
])
def test_b5_a_change_word_straight_after_the_amount_is_a_change(env, line):
    p = page("euros (EUR)", line)
    refused(run(env, live_spec(figs=REV), p, ans(TAR, {"revenue": fig("EUR 1.3 million", "Revenue", "millions", "million")})), "N2_NOT_ANCHORED")


# ------------------------------------------ F1: levels with a percentage change


@pytest.mark.parametrize("line,change", [
    ("Revenue of £16.2 million, 9% up on last year", False),
    ("Revenue was USD 16.2 million, a 9% increase", False),
    ("Revenue was USD 16.2 million, a 9% increase over the prior-year quarter", False),
    ("Revenue was USD 16.2 million, 9% higher than in the prior-year quarter", False),
    ("Revenue of EUR 16.2 million, an increase of 9% over the prior year", False),
    ("Revenue of EUR 16.2 million, up 9% on the prior year", False),
    ("Revenue of EUR 16.2 million, compared with EUR 14.9 million", False),
    ("Revenue of EUR 16.2 million, up on 2025", True),  # cannot tell a level from a change: refused
])
def test_f1_change_after_on_level_sentences(env, mod, line, change):
    rest = mod._norm(line).split("16.2 million", 1)[1]
    assert mod._change_after(rest) is change


@pytest.mark.parametrize("line", ["Revenue was USD 16.2 million, a 9% increase over the prior-year quarter",
                                  "Revenue was USD 16.2 million, 9% higher than in the prior-year quarter"])
def test_f1_levels_with_a_percentage_read(env, line):
    p = page("US dollars (USD)", line)
    read_ok(run(env, live_spec(figs=REV, currency="USD"), p, ans(TAR, {"revenue": fig("USD 16.2 million", "Revenue", "millions", "million")}, currency="USD")),
            "revenue", "16200000")


# ------------------------------------------------- F2-F5, B8, N1


def test_f2_in_1000_stores_is_prose(env, mod):
    assert mod._heading_scales(mod._norm("We now trade in 1,000 stores across Europe."), "EUR") == set()
    p = page("euros (EUR)", "All figures in EUR million.", "We now trade in 1,000 stores across Europe.", "Revenue 16.2 14.9")
    read_ok(run(env, live_spec(figs=REV), p, ans(TAR, {"revenue": fig("16.2", "Revenue", "millions", "EUR million")})), "revenue", "16200000")


@pytest.mark.parametrize("cur,heading,mult", [("PLN", "(in thousands of Polish zlotys)", 10**3), ("HUF", "(in millions of Hungarian forints)", 10**6),
                                              ("MYR", "(in thousands of Malaysian ringgit)", 10**3), ("THB", "(in thousands of Thai baht)", 10**3)])
def test_f3_more_money_nouns(env, mod, cur, heading, mult):
    assert mod._heading_scales(mod._norm(heading), cur) == {mult}


@pytest.mark.parametrize("row", ["million 30 Sep 2026 31 Dec 2025", "(million) 30 Sep 2026 31 Dec 2025", "Thousand 2026 2025"])
def test_b8_the_first_word_of_a_line_is_scanned(env, mod, row):
    assert mod._loose_scales(mod._page_lines(row + "\n"), "EUR") != set()


def test_b8_a_second_table_in_millions_refuses_a_thousands_copy(env):
    p = page("euros (EUR)", "All figures in EUR thousands.", "Revenue 15,240 14,880", "Balance sheet", "million 30 Sep 2026 31 Dec 2025", "Total borrowings 48.0 49.5")
    tb = one("tb", "Total borrowings")
    refused(run(env, live_spec(figs=tb), p, ans(TAR, {"tb": fig("48.0", "Total borrowings", "thousands", "EUR thousands")})), "N2_UNITS_MISSING")


def test_n1_mil_is_refused(env, mod):
    assert mod._own_scale(mod._norm("Receita: BRL 950 mil"), "950", "BRL") == {0}


def test_f4_an_outlook_year_ending_does_not_refuse_this_page(env, mod):
    ends = [mod._parse_minute("2027-01-01 00:00"), mod._parse_minute("2027-07-01 00:00"), mod._parse_minute("2028-01-01 00:00")]
    p = "Results for the year ended 31 December 2026\nRevenue 15,240 14,880\nWe expect mid-single-digit growth for the year ending 31 December 2027.\n"
    assert mod._period_on_page(mod._page_lines(p), ends[0], ends[1:]) is True


def test_f4_next_period_results_still_refuse(env, mod):
    ends = [mod._parse_minute("2027-01-01 00:00"), mod._parse_minute("2027-07-01 00:00")]
    p = "Results for the year ended 31 December 2026\nResults for the six months to 30 June 2027\n"
    assert mod._period_on_page(mod._page_lines(p), ends[0], ends[1:]) is False
