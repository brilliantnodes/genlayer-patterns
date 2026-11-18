"""Regression tests for the eighth independent review of 18 Nov 2026 (v10).
Pages are shaped like Studio's render (one line per row, cells joined by one
space). Every company, page and figure is fictional.
"""

import json

import pytest

from tests.direct.test_report_reader import env, mod, register  # noqa: F401
from tests.direct.test_report_reader_review import TAR, live_spec, fig, ans, run, refused  # noqa: F401
from tests.direct.test_report_reader_review4 import REV
from tests.direct.test_report_reader_review7 import page, one, read_ok


def raw_fig(**kw):
    f = {"key": "x", "label_hint": "Revenue", "labels": ["Revenue"], "ltm": False, "decimals": 0, "step": 1, "rounding": "down", "sign": "as_printed"}
    f.update(kw)
    return f


def raw_spec(f):
    s = live_spec()
    s["figures"] = [f]  # as written: nothing stated for the author
    return json.dumps(s)


# ------------------------------------------- S1: per_share is stated for every figure and agrees with the wording


def test_s1_per_share_has_no_default(env):
    with pytest.raises(Exception, match="per_share must be true .* or false .*; it has no default"):
        register(env, raw=raw_spec(raw_fig()))
    assert register(env, raw=raw_spec(raw_fig(per_share=False)))["spec"]["figures"][0]["per_share"] is False


@pytest.mark.parametrize("labels,hint", [(["Diluted"], "Diluted"), (["Basic and diluted"], "Basic and diluted"), (["Class A"], "Class A"), (["Revenue"], "Revenue")])
def test_s1_per_share_true_needs_the_wording(env, labels, hint):
    with pytest.raises(Exception, match="per_share is true, so a label or the label_hint must say so"):
        register(env, raw=raw_spec(raw_fig(labels=labels, label_hint=hint, per_share=True)))


@pytest.mark.parametrize("labels,hint", [(["Diluted"], "Net income per share, diluted"), (["Class A"], "Net asset value per unit, Class A"),
                                         (["Diluted EPS"], "Diluted"), (["Diluted", "Diluted earnings per share"], "Diluted")])
def test_s1_per_share_true_with_the_wording_in_a_label_or_the_hint(env, labels, hint):
    f = register(env, raw=raw_spec(raw_fig(labels=labels, label_hint=hint, per_share=True, decimals=2)))["spec"]["figures"][0]
    assert f["per_share"] is True


@pytest.mark.parametrize("labels,hint", [(["Diluted"], "Net income per share, diluted"), (["Earnings per share"], "EPS"), (["Diluted", "NAV/share"], "Diluted")])
def test_s1_the_wording_needs_per_share_true(env, labels, hint):
    with pytest.raises(Exception, match="reads as per share"):
        register(env, raw=raw_spec(raw_fig(labels=labels, label_hint=hint, per_share=False)))


def us_10q(row):
    return page("US dollars (USD)", "Condensed income statement (in thousands, except per share data)", "Quarter ended 2026-11-18 08:15 UTC Prior quarter",
                "Revenue 15,240 14,880", "Net income per share:", row)


def test_s1_a_diluted_row_declared_per_share_never_takes_the_heading(env):
    figs = one("eps", "Diluted", decimals=2, per_share=True, label_hint="Net income per share, diluted")
    p = us_10q("Diluted $ 0.51 $ 0.47")
    refused(run(env, live_spec(figs=figs, currency="USD"), p, ans(TAR, {"eps": fig("0.51", "Diluted", "thousands", "in thousands, except per share data")}, currency="USD")),
            "N2_UNITS_MISSING")
    read_ok(run(env, live_spec(figs=figs, currency="USD"), p, ans(TAR, {"eps": fig("0.51", "Diluted", "units", "$")}, currency="USD")), "eps", "51")


# ------------------------------------------- S3: a scale glued to the currency code after the value


@pytest.mark.parametrize("cur,curw,line,value,scale,st,stored", [
    ("EUR", "euros (EUR)", "Revenue 16.2 EURm", "16.2", "millions", "EURm", "16200000"),
    ("USD", "US dollars (USD)", "Revenue 1.2 USDbn", "1.2", "billions", "USDbn", "1200000000"),
    ("EUR", "euros (EUR)", "Revenue 15,240 EURk", "15,240", "thousands", "EURk", "15240000"),
])
def test_s3_a_glued_code_and_scale_after_the_value_is_its_own(env, cur, curw, line, value, scale, st, stored):
    hd = "All figures in EUR thousands." if scale != "thousands" else "All figures in EUR millions."
    hd = hd.replace("EUR", cur)
    p = page(curw, hd, "Operating costs 9,100 8,900", line)
    read_ok(run(env, live_spec(figs=REV, currency=cur), p, ans(TAR, {"revenue": fig(value, "Revenue", scale, st)}, currency=cur)), "revenue", stored)
    other = "thousands" if scale != "thousands" else "millions"
    refused(run(env, live_spec(figs=REV, currency=cur), p, ans(TAR, {"revenue": fig(value, "Revenue", other, hd)}, currency=cur)), "N2_UNITS_MISSING")


def test_s3_own_scale(mod):
    assert mod._own_scale("revenue 16.2 eurm", "16.2", "EUR") == {10**6}
    assert mod._own_scale("revenue 16.2 eur", "16.2", "EUR") == set()
    assert mod._own_scale("revenue 16.2 europe", "16.2", "EUR") == set()
    assert mod._own_scale("revenue 16.2 million", "16.2", "EUR") == {10**6}


# ------------------------------------------- N1: the per-share line is checked from its label to its value


@pytest.mark.parametrize("line", ["Net profit EUR 16.2 million; Diluted EPS EUR 1.23", "9M 2026 | Diluted EPS EUR 1.23"])
def test_n1_a_scale_before_the_label_does_not_count(env, line):
    figs = one("eps", "Diluted EPS", decimals=2)
    p = page("euros (EUR)", line)
    r = run(env, live_spec(figs=figs), p, ans(TAR, {"eps": fig("1.23", "Diluted EPS", "units", "EUR")}))
    assert r["kind"] != "NO_READING" or r["reason"] != "N2_UNITS_MISSING", r


def test_n1_a_scale_between_the_label_and_the_value_still_refuses(env):
    figs = one("x", "Average revenue per unit", decimals=2)
    p = page("euros (EUR)", "Quarter ended 2026-11-18 08:15 UTC Prior quarter", "Average revenue per unit (EUR thousands) 1,250 1,190")
    refused(run(env, live_spec(figs=figs), p, ans(TAR, {"x": fig("1,250", "Average revenue per unit", "units", "EUR")})), "N2_UNITS_MISSING")


# ------------------------------------------- N2 / N3: what counts as the bare currency of a per-share figure


@pytest.mark.parametrize("label,st", [("Basic earnings per share c€", "€"), ("Basic earnings per share (c€)", "€")])
def test_n2_a_symbol_after_a_letter_is_not_bare(env, label, st):
    p = page("euros (EUR)", "Quarter ended 2026-11-18 08:15 UTC Prior quarter", f"{label} 85.0 79.5")
    refused(run(env, live_spec(figs=one("eps", label, decimals=2)), p, ans(TAR, {"eps": fig("85.0", label, "units", st)})), "N2_UNITS_MISSING")


@pytest.mark.parametrize("label,cells,st,ok", [("Diluted earnings per share (US$)", "0.45 0.41", "US$", True), ("Diluted earnings per share US$", "0.45 0.41", "US$", True),
                                               ("Diluted earnings per share (US$)", "0.45 0.41", "$", False), ("Diluted earnings per share", "$ 0.45 $ 0.41", "$", True),
                                               ("Diluted earnings per share (A$)", "0.45 0.41", "$", False)])
def test_n2_us_dollars(env, label, cells, st, ok):
    # 'US$' reads when it is part of the label (between a label and its value only the bare '$' anchors); '$' is not bare in 'US$' or 'A$'
    p = page("US dollars (USD)", "Quarter ended 2026-11-18 08:15 UTC Prior quarter", f"{label} {cells}")
    r = run(env, live_spec(figs=one("eps", label, decimals=2), currency="USD"), p, ans(TAR, {"eps": fig("0.45", label, "units", st)}, currency="USD"))
    if ok:
        read_ok(r, "eps", "45")
    else:
        refused(r, "N2_UNITS_MISSING")


@pytest.mark.parametrize("st", ["EURm", "EURk", "EURbn", "EURmn"])
def test_n3_a_code_with_a_scale_suffix_is_not_the_currency(env, st):
    label = "Dividend per share"
    p = page("euros (EUR)", "Quarter ended 2026-11-18 08:15 UTC Prior quarter", f"{label} EUR 0.45 Dividends paid {st} 12.3")
    refused(run(env, live_spec(figs=one("dps", label, decimals=2)), p, ans(TAR, {"dps": fig("0.45", label, "units", st)})), "N2_UNITS_MISSING")


@pytest.mark.parametrize("st", ["EUR", "€", "(EUR)", "euro", "euros", "in EUR"])
def test_n3_the_currency_forms_that_read(env, st):
    label = "Dividend per share"
    printed = "(in EUR)" if st == "in EUR" else st
    p = page("euros (EUR)", "Quarter ended 2026-11-18 08:15 UTC Prior quarter", f"{label} {printed} 0.45 0.41")
    read_ok(run(env, live_spec(figs=one("dps", label, decimals=2)), p, ans(TAR, {"dps": fig("0.45", label, "units", st)})), "dps", "45")


# ------------------------------------------- every entry of the word lists (the review's spot mutants)

SUBUNITS = ["cent", "cents", "pence", "penny", "ct", "cts", "eurocent", "eurocents", "cps", "fils", "halala", "halalas", "halalah", "baisa", "baisas", "paise",
            "paisa", "kopeck", "kopecks", "kopek", "kopeks", "kopeyka", "kopeyki", "centime", "centimes", "groszy", "grosz", "satang", "agorot", "haleru", "kurus"]


@pytest.mark.parametrize("word", SUBUNITS)
def test_every_sub_unit_word_refuses(env, mod, word):
    assert mod._subunit(f"basic earnings per share ({word})") is True
    label = f"Basic earnings per share EUR {word}"
    p = page("euros (EUR)", "Quarter ended 2026-11-18 08:15 UTC Prior quarter", f"{label} 45.2 41.0")
    refused(run(env, live_spec(figs=one("eps", label, decimals=2)), p, ans(TAR, {"eps": fig("45.2", label, "units", "EUR")})), "N2_UNITS_MISSING")


def test_the_sub_unit_list_is_the_one_tested(mod):
    assert sorted(mod.SUBUNIT_WORDS) == sorted(SUBUNITS)


PER_WORDS = ["share", "shares", "unit", "units", "ads", "adr", "adrs", "ordinary", "stapled", "security", "securities", "gdr", "gdrs", "depositary", "depository",
             "stock"]


@pytest.mark.parametrize("word", PER_WORDS)
def test_every_share_word_reads_as_per_share(mod, word):
    assert mod._per_share_label(f"net income per {word}") is True
    assert mod._per_share_label(f"net income per diluted class a {word}") is True


def test_the_share_word_list_is_the_one_tested(mod):
    assert sorted(mod.PER_WHAT) == sorted(PER_WORDS)


@pytest.mark.parametrize("before", ["per", "sq", "square", "cubic", "class", "series", "tranche"])
def test_every_area_or_class_word_stops_a_one_letter_scale(mod, before):
    assert mod._heading_scales(mod._norm(f"Average rent {before} m EUR 7.25"), "EUR") == set()
    assert mod._heading_scales(mod._norm(f"Notes {before} k EUR 7.25"), "EUR") == set()


def test_a_dot_after_a_number_ends_it(env, mod):
    # 'up on 2025.' is a year, not an amount: a change
    assert mod._change_after(", up on 2025.") is True
    assert mod._change_after(", up on 2025. it") is True
    p = page("euros (EUR)", "Revenue was EUR 1.3 million, up on 2025.")
    refused(run(env, live_spec(figs=REV), p, ans(TAR, {"revenue": fig("EUR 1.3 million", "Revenue", "millions", "million")})), "N2_NOT_ANCHORED")
