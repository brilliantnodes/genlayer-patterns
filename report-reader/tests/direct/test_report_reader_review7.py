"""Regression tests for the seventh independent review of 18 Nov 2026 (v8)
and for mutation run v9. Each shows the page that used to store a wrong
figure or refuse a correct one, and what it does now. Pages are shaped like
Studio's render (one line per row, cells joined by one space). Every
company, page and figure is fictional.
"""

import pytest

from tests.direct.test_report_reader import env, mod  # noqa: F401
from tests.direct.test_report_reader_review import TAR, live_spec, fig, ans, run, refused  # noqa: F401
from tests.direct.test_report_reader_review4 import REV, head


def read_ok(r, key, value):
    assert r["kind"] == "READ", r
    assert r["figures"][key] == value, r


def one(key, label, **kw):
    f = {"key": key, "label_hint": "".join(c for c in label if c.isalnum() or c in " ,.()-/'&%:"), "labels": [label], "ltm": False, "decimals": 0,
         "step": 1, "rounding": "down", "sign": "as_printed"}
    f.update(kw)
    return [f]


END = "Results for the quarter ended 2026-11-18 08:15 UTC."


def page(cur_words, *lines):
    return f"{TAR}\nQuarterly results\n{END} All amounts in {cur_words}.\n" + "\n".join(lines) + "\n"


# ------------------------------------------- mutation run v9: 'mln', 'bln', 'Mrd' in a second table's heading

FIRST = "All figures in EUR thousands unless stated otherwise."


def two_tables(second):
    return head(FIRST) + "Revenue 15,240 14,880\nOperating costs (9,100) (8,900)\n" + second + "\nTotal borrowings 48.0 47.1\n"


def test_one_thousands_table_reads(env):
    p = head(FIRST) + "Revenue 15,240 14,880\nOperating costs (9,100) (8,900)\n"
    read_ok(run(env, live_spec(figs=REV), p, ans(TAR, {"revenue": fig("15,240", "Revenue", "thousands", FIRST)})), "revenue", "15240000")


@pytest.mark.parametrize("second", ["Group balance sheet in EUR mln", "Group balance sheet in EUR bln", "Group balance sheet in EUR Mrd"])
def test_a_second_table_in_mln_bln_or_mrd_refuses_a_thousands_copy(env, second):
    r = run(env, live_spec(figs=REV), two_tables(second), ans(TAR, {"revenue": fig("15,240", "Revenue", "thousands", FIRST)}))
    refused(r, "N2_UNITS_MISSING")


@pytest.mark.parametrize("heading", ["All figures in EUR mln", "All figures in EUR bln", "Figures in EUR Mrd"])
def test_a_copy_in_mln_bln_or_mrd_refuses(env, heading):
    p = head(heading) + "Revenue 15.2 14.9\n"
    scale = "billions" if heading.lower().endswith(("bln", "mrd")) else "millions"
    refused(run(env, live_spec(figs=REV), p, ans(TAR, {"revenue": fig("15.2", "Revenue", scale, heading.split(" in ")[-1])})), "N2_UNITS_MISSING")


@pytest.mark.parametrize("copied,mult", [("EUR mln", 10**6), ("mln", 10**6), ("EUR bln", 10**9), ("bln", 10**9), ("EUR Mrd", 10**9)])
def test_scale_mentions_names_mln_bln_and_mrd(mod, copied, mult):
    assert mod._scale_mentions(copied, "EUR") == {mult}


# ------------------------------------------- P7-B1: per share is declared in the report, and checked against its labels

PS_LABELS = ["Net income per diluted common share", "Earnings per basic and diluted share", "Net income per Class A common share",
             "Earnings per American depositary share", "Distribution per limited partner unit", "Distribution per stapled security",
             "Earnings per basic and diluted common share", "Net income per American depositary receipt", "Distribution per security",
             "Net asset value per A Accumulation share", "Revenue per business unit"]


def us_page(label):
    return page("US dollars (USD)", "Condensed income statement (in thousands, except per share data)", "Quarter ended 2026-11-18 08:15 UTC Prior quarter",
                "Revenue 15,240 14,880", f"{label} $ 0.45 $ 0.40")


@pytest.mark.parametrize("label", PS_LABELS + ["Earnings per share", "Basic EPS", "NAV/share", "Dividend per ordinary share", "Net income per GDR"])
def test_b1_labels_that_read_as_per_share(mod, label):
    assert mod._per_share_label(mod._norm_label(label)) is True


@pytest.mark.parametrize("label", ["Leverage as per covenant", "Revenue per employee", "Revenue per diluted employee", "Revenue per store"])
def test_b1_totals_with_per(mod, label):
    assert mod._per_share_label(mod._norm_label(label)) is False


@pytest.mark.parametrize("label", PS_LABELS)
def test_b1_a_per_share_figure_never_takes_the_thousands_heading(env, label):
    figs = one("eps", label, decimals=2)
    refused(run(env, live_spec(figs=figs, currency="USD"), us_page(label),
                ans(TAR, {"eps": fig("0.45", label, "thousands", "in thousands, except per share data")}, currency="USD")), "N2_UNITS_MISSING")
    read_ok(run(env, live_spec(figs=figs, currency="USD"), us_page(label), ans(TAR, {"eps": fig("0.45", label, "units", "$")}, currency="USD")), "eps", "45")


@pytest.mark.parametrize("label", PS_LABELS[:3] + ["Earnings per share", "Basic EPS", "NAV/share"])
def test_b1_a_per_share_label_cannot_be_declared_a_total(env, mod, label):
    from tests.direct.test_report_reader import register
    s = live_spec(figs=one("eps", label, decimals=2, per_share=False), currency="USD")
    with pytest.raises(Exception, match="per_share must be true"):
        register(env, s)


def test_b1_a_label_hint_that_reads_as_per_share_counts(env):
    from tests.direct.test_report_reader import register
    f = one("nav", "Class A", decimals=2, per_share=False)
    f[0]["label_hint"] = "Net asset value per share, Class A"
    with pytest.raises(Exception, match="per_share must be true"):
        register(env, live_spec(figs=f))


@pytest.mark.parametrize("bad", [1, 0, "true", None, [True]])
def test_b1_per_share_must_be_a_bool(env, bad):
    from tests.direct.test_report_reader import register
    with pytest.raises(Exception, match="per_share must be true or false"):
        register(env, live_spec(figs=one("eps", "Class A", decimals=2, per_share=bad)))


def test_b1_a_declared_per_share_figure_with_any_label(env):
    # a share-class row under a 'Net asset value per share' heading: the label alone says nothing
    from tests.direct.test_report_reader import register
    p = page("euros (EUR)", "Statement of net assets (EUR thousands)", "Quarter ended 2026-11-18 08:15 UTC Prior quarter",
             "Total net assets 125,400 118,900", "Net asset value per share (EUR)", "Class A EUR 112.45 EUR 108.10")
    figs = one("nav_a", "Class A", decimals=2, per_share=True)
    assert register(env, live_spec(figs=figs))["spec"]["figures"][0]["per_share"] is True
    refused(run(env, live_spec(figs=figs), p, ans(TAR, {"nav_a": fig("112.45", "Class A", "thousands", "EUR thousands")})), "N2_UNITS_MISSING")


def test_b1_a_declared_per_share_figure_reads_in_units(env):
    p = page("euros (EUR)", "Statement of net assets (EUR thousands)", "Quarter ended 2026-11-18 08:15 UTC Prior quarter",
             "Total net assets 125,400 118,900", "Net asset value per share (EUR)", "Class A EUR 112.45 EUR 108.10")
    figs = one("nav_a", "Class A", decimals=2, per_share=True)
    read_ok(run(env, live_spec(figs=figs), p, ans(TAR, {"nav_a": fig("112.45", "Class A", "units", "EUR")})), "nav_a", "11245")


def test_b1_the_same_label_as_a_total_reads_the_heading(env):
    p = page("euros (EUR)", "Statement of net assets (EUR thousands)", "Quarter ended 2026-11-18 08:15 UTC Prior quarter",
             "Total net assets 125,400 118,900", "Class A 82,310 80,100")
    figs = one("na_a", "Class A")
    read_ok(run(env, live_spec(figs=figs), p, ans(TAR, {"na_a": fig("82,310", "Class A", "thousands", "EUR thousands")})), "na_a", "82310000")


def test_b1_nav_per_class_a_share(env):
    label = "Net asset value per Class A share"
    p = page("euros (EUR)", "Statement of net assets (EUR thousands)", "Quarter ended 2026-11-18 08:15 UTC Prior quarter",
             "Total net assets 125,400 118,900", f"{label} EUR 112.45 EUR 108.10")
    figs = one("nav", label, decimals=2)
    refused(run(env, live_spec(figs=figs), p, ans(TAR, {"nav": fig("112.45", label, "thousands", "EUR thousands")})), "N2_UNITS_MISSING")
    read_ok(run(env, live_spec(figs=figs), p, ans(TAR, {"nav": fig("112.45", label, "units", "EUR")})), "nav", "11245")


@pytest.mark.parametrize("label,line", [("Average revenue per unit", "Average revenue per unit (EUR thousands) 1,250 1,190"),
                                        ("Revenue per business unit", "Revenue per business unit EUR m 3.8 3.7"),
                                        ("Dividend per share", "Dividend per share (EUR million) 0.45 0.40")])
def test_b1_a_per_share_line_with_a_scale_before_the_value_refuses(env, label, line):
    p = page("euros (EUR)", "Quarter ended 2026-11-18 08:15 UTC Prior quarter", line)
    v = line.split()[-2]
    figs = one("x", label, decimals=2)
    for scale, st in (("units", "EUR"), ("thousands", "EUR thousands"), ("millions", "EUR m")):
        r = run(env, live_spec(figs=figs), p, ans(TAR, {"x": fig(v, label, scale, st)}))
        assert r["kind"] == "NO_READING", r


@pytest.mark.parametrize("label", ["Net asset value per share Class M", "Net asset value per share Class K", "Net asset value per share Series M"])
def test_b1_a_share_class_letter_is_not_a_scale(env, label):
    p = page("euros (EUR)", "Quarter ended 2026-11-18 08:15 UTC Prior quarter", f"{label} EUR 112.45 EUR 108.10")
    read_ok(run(env, live_spec(figs=one("nav", label, decimals=2)), p, ans(TAR, {"nav": fig("112.45", label, "units", "EUR")})), "nav", "11245")


@pytest.mark.parametrize("line", ["Dividend per share in thousands EUR 0.45", "Dividend per share EUR '000 0.45",
                                  "Dividend per share thousand 0.45 EUR", "Dividend per share million 0.45 EUR"])
def test_b1_scale_words_before_a_per_share_value_refuse(env, line):
    # the last two: a scale word with no currency before the value is no heading, but still a scale
    label = "Dividend per share"
    p = page("euros (EUR)", "Quarter ended 2026-11-18 08:15 UTC Prior quarter", line)
    refused(run(env, live_spec(figs=one("dps", label, decimals=2)), p, ans(TAR, {"dps": fig("0.45", label, "units", "EUR")})), "N2_UNITS_MISSING")


def test_b1_a_currency_after_a_per_share_value_reads(env):
    label = "Dividend per share"
    p = page("euros (EUR)", "Quarter ended 2026-11-18 08:15 UTC Prior quarter", f"{label} 0.45 EUR")
    read_ok(run(env, live_spec(figs=one("dps", label, decimals=2)), p, ans(TAR, {"dps": fig("0.45", label, "units", "EUR")})), "dps", "45")


def test_b1_a_scale_after_a_per_share_value_does_not_matter(env):
    label = "Dividend per share"
    p = page("euros (EUR)", "Quarter ended 2026-11-18 08:15 UTC Prior quarter", f"{label} EUR 0.45 Dividends paid (EUR m) 12.3")
    read_ok(run(env, live_spec(figs=one("dps", label, decimals=2)), p, ans(TAR, {"dps": fig("0.45", label, "units", "EUR")})), "dps", "45")


@pytest.mark.parametrize("label,st", [("Basic earnings per share (AED fils)", "AED"), ("Basic earnings per share (RUB kopecks)", "RUB"),
                                      ("Basic earnings per share AUD cps", "AUD"), ("Basic earnings per share (INR paise)", "INR")])
def test_b5_a_per_share_figure_in_other_sub_units_refuses(env, label, st):
    # the sub-unit is part of the label, so the value anchors; the bare code beside it is not the figure's unit
    p = page(f"the report's currency ({st})", "Quarter ended 2026-11-18 08:15 UTC Prior quarter", f"{label} 45.2 41.0")
    refused(run(env, live_spec(figs=one("eps", label, decimals=2), currency=st), p, ans(TAR, {"eps": fig("45.2", label, "units", st)}, currency=st)),
            "N2_UNITS_MISSING")


# ------------------------------------------- P7-B2: a decimal percentage after 'or'


@pytest.mark.parametrize("line", [
    "Revenue was USD 1.3 million, or 9.3%, higher than in the prior-year quarter.",
    "Revenue was USD 1.3 million or 9.3% lower than in the prior-year quarter.",
    "Revenue was USD 1.3 million, or 9.3 per cent, above the prior year.",
    "Revenue was USD 1.3 million, or 9%, higher than in the prior-year quarter.",
])
def test_b2_or_and_a_decimal_percentage_is_a_change(env, line):
    p = page("US dollars (USD)", line)
    refused(run(env, live_spec(figs=REV, currency="USD"), p, ans(TAR, {"revenue": fig("USD 1.3 million", "Revenue", "millions", "million")}, currency="USD")),
            "N2_NOT_ANCHORED")


@pytest.mark.parametrize("line", ["Revenue was EUR 16.2 million, up 9.3% on the prior year", "Revenue was EUR 16.2 million, a 9.3% increase",
                                  "Revenue was EUR 16.2 million, 9.3% higher than last year", "Revenue was EUR 16.2 million, up from EUR 14.9 million"])
def test_b2_a_level_with_a_decimal_percentage_reads(env, line):
    p = page("euros (EUR)", line)
    read_ok(run(env, live_spec(figs=REV), p, ans(TAR, {"revenue": fig("EUR 16.2 million", "Revenue", "millions", "million")})), "revenue", "16200000")


def test_b2_decimal_percentage_tokens(mod):
    assert mod._change_after(mod._norm(", or 9.3%, higher")) is True
    assert mod._change_after(mod._norm(", up 9.3%")) is False
    assert mod._change_after(mod._norm(", up 14.9 on the prior year")) is False


# ------------------------------------------- P7-B3 / P7-F3: a multiplier heading with words after it


@pytest.mark.parametrize("cur,h", [("EUR", "(in EUR 1,000, unless otherwise stated)"), ("EUR", "(x EUR 1,000, except per share data)"),
                                   ("EUR", "Amounts in € 1,000 unless otherwise stated"), ("USD", "(in 1,000 US dollars)"), ("USD", "(x 1,000 dollars)")])
def test_b3_multiplier_heading_with_trailing_words(mod, cur, h):
    assert mod._heading_scales(mod._norm(h), cur) == {10**3}
    assert mod._loose_scales(mod._page_lines(h + "\n"), cur) == {10**3}


@pytest.mark.parametrize("prose", ["We now trade in 1,000 stores across Europe.", "Staff numbers rose to more than x 1,000 people."])
def test_b3_in_a_number_and_a_noun_is_prose(mod, prose):
    assert mod._page_scales(mod._page_lines(prose + "\n"), "EUR") == set()


def test_f3_one_heading_page_reads_the_faithful_copy(env):
    p = page("euros (EUR)", "Condensed income statement (in EUR 1,000, unless otherwise stated)", "Revenue 15,240 14,880")
    read_ok(run(env, live_spec(figs=REV), p, ans(TAR, {"revenue": fig("15,240", "Revenue", "thousands", "in EUR 1,000")})), "revenue", "15240000")


def test_b3_two_table_page_refuses_the_other_scale(env):
    p = page("euros (EUR)", "Key figures (EUR million)", "Total borrowings 48.0 49.5",
             "Condensed income statement (in EUR 1,000, unless otherwise stated)", "Revenue 15,240 14,880")
    refused(run(env, live_spec(figs=REV), p, ans(TAR, {"revenue": fig("15,240", "Revenue", "millions", "EUR million")})), "N2_UNITS_MISSING")


# ------------------------------------------- P7-B4: 'mil' in a heading


@pytest.mark.parametrize("second", ["Balance sheet (EUR mil)", "Balance sheet (R$ mil)"])
def test_b4_a_mil_heading_keeps_every_scaled_copy_out(env, mod, second):
    p = page("euros (EUR)", "Income statement (EUR thousands)", "Revenue 15,240 14,880", second, "Total borrowings 48.0 49.5")
    tb = one("tb", "Total borrowings")
    refused(run(env, live_spec(figs=tb), p, ans(TAR, {"tb": fig("48.0", "Total borrowings", "thousands", "EUR thousands")})), "N2_UNITS_MISSING")
    refused(run(env, live_spec(figs=REV), p, ans(TAR, {"revenue": fig("15,240", "Revenue", "thousands", "EUR thousands")})), "N2_UNITS_MISSING")
    assert 0 in mod._loose_scales(mod._page_lines(second + "\n"), "EUR")


def test_b4_mil_after_a_number_is_that_amounts_own(mod):
    assert 0 not in mod._loose_scales(mod._page_lines("Revenue EUR 950 mil\n"), "EUR")


# ------------------------------------------- P7-B5 / P7-N4: the per-share currency copy


@pytest.mark.parametrize("label,st", [("Basic earnings per share (€c)", "€"), ("Basic earnings per share €c", "€"),
                                      ("Basic earnings per share (EURc)", "EUR")])
def test_b5_a_currency_copied_from_a_cents_mark_refuses(env, label, st):
    p = page("euros (EUR)", "Quarter ended 2026-11-18 08:15 UTC Prior quarter", f"{label} 45.2 41.0")
    refused(run(env, live_spec(figs=one("eps", label, decimals=2)), p, ans(TAR, {"eps": fig("45.2", label, "units", st)})), "N2_UNITS_MISSING")


@pytest.mark.parametrize("line,st", [("Basic earnings per share (€) 0.45 0.41", "€"), ("Basic earnings per share (in EUR) 0.45 0.41", "(in EUR)"),
                                     ("Basic earnings per share (in EUR) 0.45 0.41", "in EUR"), ("Basic earnings per share EUR 0.45 EUR 0.41", "EUR")])
def test_n4_a_bare_currency_copy_reads(env, line, st):
    label = "Basic earnings per share"
    p = page("euros (EUR)", "Quarter ended 2026-11-18 08:15 UTC Prior quarter", line)
    read_ok(run(env, live_spec(figs=one("eps", label, decimals=2)), p, ans(TAR, {"eps": fig("0.45", label, "units", st)})), "eps", "45")


def test_bare_on_line(mod):
    assert mod._bare_on_line("eps (€c) 45.2", "€") is False
    assert mod._bare_on_line("eps (€) 45.2", "€") is True
    assert mod._bare_on_line("eps r$ 0.45", "r$") is True
    assert mod._bare_on_line("eps teur 0.45", "eur") is False
    assert mod._bare_on_line("eps eur1 0.45", "eur") is False
    assert mod._bare_on_line("eps", "") is False


# ------------------------------------------- P7-F2: a unit of area


@pytest.mark.parametrize("cur,curw,line", [("EUR", "euros (EUR)", "Average rent per m² EUR 7.25 EUR 7.10"),
                                           ("GBP", "pounds sterling (GBP)", "Average rent per sq m £12.50 £12.10"),
                                           ("EUR", "euros (EUR)", "Average water tariff per m³ € 1.85 € 1.80"),
                                           ("EUR", "euros (EUR)", "Average rent per square m EUR 7.25 EUR 7.10")])
def test_f2_rent_per_square_metre_names_no_heading(env, mod, cur, curw, line):
    assert mod._heading_scales(mod._norm(line), cur) == set()
    hd = "All figures in EUR thousands." if cur == "EUR" else "All figures in £000."
    st = "EUR thousands" if cur == "EUR" else "£000"
    p = page(curw, hd, "Revenue 15,240 14,880", line)
    read_ok(run(env, live_spec(figs=REV, currency=cur), p, ans(TAR, {"revenue": fig("15,240", "Revenue", "thousands", st)}, currency=cur)), "revenue", "15240000")


def test_f2_class_m_eur_names_no_heading(mod):
    assert mod._heading_scales(mod._norm("Net asset value per share Class M EUR 112.45"), "EUR") == set()
    assert mod._heading_scales(mod._norm("Tranche K EUR 1,000 notes"), "EUR") == set()


def test_f2_m_eur_still_a_heading(mod):
    assert mod._heading_scales(mod._norm("Key figures m EUR"), "EUR") == {10**6}
    assert mod._heading_scales(mod._norm("Key figures (EUR m)"), "EUR") == {10**6}


# ------------------------------------------- P7-N1 / P7-F4: a spaced dash after the amount is a comma


def test_n1_dash_and_comma_agree(env, mod):
    assert mod._change_after(" - a year-on-year increase") is True  # the rest of a normalised line keeps its leading space
    assert mod._change_after(", a year-on-year increase") is True
    assert mod._change_after(" - up 9% on last year") is False
    p = page("euros (EUR)", "Revenue: EUR 1.3 million – a year-on-year increase")
    refused(run(env, live_spec(figs=REV), p, ans(TAR, {"revenue": fig("EUR 1.3 million", "Revenue", "millions", "million")})), "N2_NOT_ANCHORED")


def test_f4_dash_then_a_level(env):
    p = page("pounds sterling (GBP)", "Revenue of £16.2m – up 9% on last year")
    read_ok(run(env, live_spec(figs=REV, currency="GBP"), p, ans(TAR, {"revenue": fig("£16.2m", "Revenue", "millions", "m")}, currency="GBP")), "revenue", "16200000")


@pytest.mark.parametrize("cur,curw,line,value", [
    ("EUR", "euros (EUR)", "Revenue of EUR 16.2 million up 9% on the prior year", "EUR 16.2 million"),
    ("USD", "US dollars (USD)", "Revenue of USD 16.2 million increased 9% year over year", "USD 16.2 million"),
])
def test_f4_a_change_word_straight_after_a_level_still_refuses(env, cur, curw, line, value):
    p = page(curw, line)
    refused(run(env, live_spec(figs=REV, currency=cur), p, ans(TAR, {"revenue": fig(value, "Revenue", "millions", "million")}, currency=cur)), "N2_NOT_ANCHORED")


def test_a_hyphenated_word_is_not_a_dash(mod):
    assert mod._change_after(mod._norm(" year-on-year increase")) is True
    assert mod._change_after(mod._norm(" (2025: EUR 14.9 million)")) is False


# ------------------------------------------- mutation run v10: the cent sign is the only mark


@pytest.mark.parametrize("line", ["Quarterly dividend per share (USD) 4.5¢ 4.2¢", "Quarterly dividend per share USD 4.5¢ USD 4.2¢"])
def test_the_cent_sign_beside_a_bare_code_refuses(env, line):
    label = "Quarterly dividend per share"
    p = page("US dollars (USD)", "Quarter ended 2026-11-18 08:15 UTC Prior quarter", line)
    refused(run(env, live_spec(figs=one("dps", label, decimals=2), currency="USD"), p, ans(TAR, {"dps": fig("4.5", label, "units", "USD")}, currency="USD")),
            "N2_UNITS_MISSING")


def test_the_same_line_in_dollars_reads(env):
    label = "Quarterly dividend per share"
    p = page("US dollars (USD)", "Quarter ended 2026-11-18 08:15 UTC Prior quarter", f"{label} (USD) 0.045 0.042")
    read_ok(run(env, live_spec(figs=one("dps", label, decimals=3), currency="USD"), p, ans(TAR, {"dps": fig("0.045", label, "units", "USD")}, currency="USD")),
            "dps", "45")


# ------------------------------------------- mutation run v10: paths no earlier test reached


def test_trillion_after_the_value_refuses_a_billions_copy(env):
    p = page("euros (EUR)", "All figures in EUR billions.", "Assets under administration EUR 1.2 trillion")
    figs = one("aua", "Assets under administration")
    refused(run(env, live_spec(figs=figs), p, ans(TAR, {"aua": fig("1.2", "Assets under administration", "billions", "EUR billions")})), "N2_UNITS_MISSING")


@pytest.mark.parametrize("line", ["Revenue was EUR 1.3 million, up on last year at 16.2 million",
                                  "Revenue was EUR 1.3 million, up on prior year to 16.2 million"])
def test_up_on_last_year_at_an_amount_is_a_change(env, line):
    p = page("euros (EUR)", line)
    refused(run(env, live_spec(figs=REV), p, ans(TAR, {"revenue": fig("EUR 1.3 million", "Revenue", "millions", "million")})), "N2_NOT_ANCHORED")


@pytest.mark.parametrize("line", ["Dividend per share EUR 0.45 million", "Dividend per share EUR 0.45 m"])
def test_a_per_share_value_with_its_own_scale_word_refuses(env, line):
    label = "Dividend per share"
    p = page("euros (EUR)", "Quarter ended 2026-11-18 08:15 UTC Prior quarter", line)
    refused(run(env, live_spec(figs=one("dps", label, decimals=2)), p, ans(TAR, {"dps": fig("0.45", label, "units", "EUR")})), "N2_UNITS_MISSING")
