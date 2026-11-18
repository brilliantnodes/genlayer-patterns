"""Regression tests for the ninth independent review of 18 Nov 2026 (v10).
Pages are shaped like Studio's render (one line per row, cells joined by one
space); the footnote-mark tests use what Studio returned for
https://privatecredit.brilliantnodes.com/report-reader/render-sup.html in
text and in HTML mode. Every company, page and figure is fictional.
"""

import json

import pytest

from tests.direct.test_report_reader import env, mod, register, read, tick, answer, spec, OPEN0, CLOSE0, ENDS, LAG, WIN, T0, URL_T, PAGE  # noqa: F401
from tests.direct.test_report_reader import iso
from tests.direct.test_report_reader_review import TAR, E0, live_spec, fig, ans, run, refused  # noqa: F401
from tests.direct.test_report_reader_review4 import REV, head
from tests.direct.test_report_reader_review7 import page, one, read_ok

OST = "Ostravelle Fibre SA"
TH = "All figures in EUR thousands unless stated otherwise.\n"
LTM = [{"key": "ltm_ebitda", "label_hint": "EBITDA for the last twelve months", "labels": ["EBITDA (last twelve months)"], "ltm": True,
        "decimals": 0, "step": 1000, "rounding": "down", "sign": "as_printed"}]
EBITDA = one("ebitda", "EBITDA")


def adjusted_page(prefix):
    return (f"{OST}\nQuarterly results\nResults for the quarter ended 2026-11-18 08:15 UTC.\n{TH}"
            "Quarter ended 2026-11-18 08:15 UTC Prior quarter\nRevenue 8,315 8,020\n"
            f"{prefix} EBITDA (last twelve months) 2,390.0 2,250.5\nNet finance costs (910) (955)\n"
            f"{prefix} EBITDA excludes restructuring costs.\n")


# ------------------------------------------- B1: an abbreviation is not a list number


@pytest.mark.parametrize("prefix", ["Adjusted", "Adj.", "Und.", "Rep.", "Est.", "Org.", "PF.", "Excl.", "Norm.", "(excl. IFRS 16)", "Note 4."])
def test_b1_a_qualified_ebitda_is_not_the_plain_one(env, prefix):
    r = run(env, live_spec(OST, LTM), adjusted_page(prefix), ans(OST, {"ltm_ebitda": fig("2,390.0", "EBITDA (last twelve months)", ltm="yes")}))
    refused(r, "N2_NOT_ANCHORED")


@pytest.mark.parametrize("prefix", ["1.", "12.", "a)", "b.", "iv.", "ii)", "x."])
def test_b1_a_list_number_at_the_start_of_the_line_still_reads(env, prefix):
    p = head("All figures in EUR thousands unless stated otherwise.") + f"{prefix} Revenue 15,240 14,880\n"
    read_ok(run(env, live_spec(figs=REV), p, ans(TAR, {"revenue": fig("15,240", "Revenue", "thousands", "EUR thousands")})), "revenue", "15240000")


def test_b1_starts_phrase(mod):
    assert mod._starts_phrase("adj. ebitda 2,390", 5) is False
    assert mod._starts_phrase("est. ebitda 2,390", 5) is False
    assert mod._starts_phrase("1. ebitda 2,390", 3) is True
    assert mod._starts_phrase("iv. ebitda 2,390", 4) is True
    assert mod._starts_phrase("a) ebitda 2,390", 3) is True
    assert mod._starts_phrase("total 1. ebitda 2,390", 9) is False       # a number in the middle of the line is not a list number
    assert mod._starts_phrase("segment | 1. ebitda 2,390", 13) is True   # the number starts its cell
    assert mod._starts_phrase("adjusted ebitda 2,390", 9) is False
    assert mod._starts_phrase("ab) ebitda", 4) is False                  # two letters: not a list letter
    assert mod._starts_phrase("vi) ebitda", 4) is True                   # a roman numeral


@pytest.mark.parametrize("line", ["Adjusted: EBITDA 2,390 2,250", "Adjusted* EBITDA 2,390 2,250", "Non-GAAP - EBITDA 2,390 2,250", "Pro forma: EBITDA 2,390 2,250",
                                  "Guidance: EBITDA 2,390 2,250", "Underlying | EBITDA 2,390 2,250", "Prior year: EBITDA 2,390 2,250",
                                  "Like-for-like - EBITDA 2,390 2,250", "Constant currency: EBITDA 2,390 2,250", "Budget; EBITDA 2,390 2,250"])
def test_b1_a_qualifier_before_a_mark_does_not_start_a_phrase(env, line):
    p = head("All figures in EUR thousands unless stated otherwise.") + "Revenue 8,315 8,020\n" + line + "\n"
    refused(run(env, live_spec(figs=EBITDA), p, ans(TAR, {"ebitda": fig("2,390", "EBITDA", "thousands", "EUR thousands")})), "N2_NOT_ANCHORED")


@pytest.mark.parametrize("line", ["Highlights: EBITDA 2,390 2,250", "Q3 - EBITDA 2,390 2,250", "Group | EBITDA 2,390 2,250", "* EBITDA 2,390 2,250", "- EBITDA 2,390 2,250"])
def test_b1_a_plain_lead_before_a_mark_still_reads(env, line):
    p = head("All figures in EUR thousands unless stated otherwise.") + "Revenue 8,315 8,020\n" + line + "\n"
    read_ok(run(env, live_spec(figs=EBITDA), p, ans(TAR, {"ebitda": fig("2,390", "EBITDA", "thousands", "EUR thousands")})), "ebitda", "2390000")


QUALS = ["adjusted", "adj", "underlying", "normalised", "normalized", "pro forma", "proforma", "non gaap", "non ifrs", "guidance", "target", "forecast",
         "budget", "outlook", "estimate", "estimated", "est", "expected", "organic", "comparable", "recurring", "core", "restated", "excluding", "excl",
         "constant currency", "like for like", "prior", "previous", "comparative", "prior year", "previous year", "last year", "year ago", "prior period",
         "previous period", "prior quarter", "previous quarter"]


@pytest.mark.parametrize("q", QUALS)
def test_every_qualifier_counts(mod, q):
    assert mod._qualifier_before(f"segment a {q}") is True
    assert mod._starts_phrase(f"{q}: ebitda 2,390", len(q) + 2) is False


def test_the_qualifier_list_is_the_one_tested(mod):
    assert sorted(mod.QUALIFIERS) == sorted(QUALS)
    assert mod._qualifier_before("highlights") is False and mod._qualifier_before("") is False and mod._qualifier_before("unadjusted") is False


# ------------------------------------------- per-share abbreviations


@pytest.mark.parametrize("label", ["NAVPS", "BVPS", "DPU", "NAVPU", "Diluted EPS", "DPS", "Earnings per common stock", "Net income per share of common stock"])
def test_per_share_abbreviations_read_as_per_share(mod, label):
    assert mod._per_share_label(mod._norm_label(label)) is True


def test_navps_never_takes_the_thousands_heading(env):
    p = page("euros (EUR)", "Statement of net assets (EUR thousands)", "Quarter ended 2026-11-18 08:15 UTC Prior quarter", "Total net assets 125,400 118,900",
             "NAVPS EUR 112.45 EUR 108.10")
    figs = one("nav", "NAVPS", decimals=2)
    refused(run(env, live_spec(figs=figs), p, ans(TAR, {"nav": fig("112.45", "NAVPS", "thousands", "EUR thousands")})), "N2_UNITS_MISSING")
    read_ok(run(env, live_spec(figs=figs), p, ans(TAR, {"nav": fig("112.45", "NAVPS", "units", "EUR")})), "nav", "11245")


# ------------------------------------------- footnote marks set in <sup> (measured on Studio)

STUDIO_HTML = """
<p>Render check for the Brilliant Nodes GenLayer demo pages (fictional figures): how footnote marks come out as text.</p>
<table>
<tbody><tr><th></th><th>Quarter</th><th>Prior quarter</th></tr>
<tr><td>Revenue<sup>1</sup></td><td>15,240</td><td>14,880</td></tr>
<tr><td>Total borrowings</td><td>48.0<sup>1</sup></td><td>47.1<sup>2</sup></td></tr>
<tr><td>Net finance costs <sup>(a)</sup></td><td>(2,150)<sup>a</sup></td><td>(2,090)</td></tr>
<tr><td>EBITDA¹</td><td>4,180²</td><td>4,020</td></tr>
<tr><td>Cash<sub>2</sub></td><td>1,205</td><td></td></tr>
<tr><td>Empty cell row</td><td></td><td>915</td></tr>
</tbody></table>
<p>Prose: revenue was EUR 16.2 million<sup>3</sup> and borrowings were EUR 48.0 million.<sup>4</sup></p>
<p>Inline <span>span</span>joined and <b>bold</b>text; a<br>line break.</p>

"""
STUDIO_TEXT = ("Render check for the Brilliant Nodes GenLayer demo pages (fictional figures): how footnote marks come out as text.\n\nQuarter Prior quarter\n"
               "Revenue1 15,240 14,880\nTotal borrowings 48.01 47.12\nNet finance costs (a) (2,150)a (2,090)\nEBITDA¹ 4,180² 4,020\nCash2 1,205\n"
               "Empty cell row 915\n\nProse: revenue was EUR 16.2 million3 and borrowings were EUR 48.0 million.4\n\nInline spanjoined and boldtext; a\nline break.")


def test_glued_marks_from_studios_html(mod):
    marks = mod._glued_marks(STUDIO_HTML)
    assert marks == {"revenue1", "48.01", "47.12", "(2,150)a", "cash2", "million3", "million.4"}
    # every glued token is printed in Studio's text render of the same page, as a whole token
    toks = set(mod._norm(STUDIO_TEXT).split(" "))
    assert marks <= toks


def test_html_text_follows_studios_text_render(mod):
    assert mod._html_text("Inline <span>span</span>joined and <b>bold</b>text; a<br>line break.") == "Inline spanjoined and boldtext; a line break."
    assert mod._html_text('lass="x">48.0') == " 48.0"                      # a piece that starts inside a tag
    assert mod._html_text("<td>15,240</td><td>48.0") == " 15,240  48.0"   # cells are apart
    assert mod._html_text("a&nbsp;b &amp; c") == "a b & c"


@pytest.mark.parametrize("html,marks", [
    ("<td>48.0<sup><a href='#n1'>1</a></sup></td>", {"48.01"}),
    ("<td><b>48.0</b><sup>1</sup></td>", {"48.01"}),
    ("<td>48.0<SUP class='fn'>1</SUP></td>", {"48.01"}),
    ("<td>48.0 <sup>1</sup></td>", set()),                 # after a space: its own token
    ("<td>48.0&nbsp;<sup>1</sup></td>", set()),
    ("<td>48.0</td><td><sup>1</sup></td>", set()),         # in the next cell
    ("<td>48.0<sup></sup></td>", set()),                   # an empty mark
    ("<td>48.0<sup>¹</sup></td>", set()),             # a Unicode superscript is dropped anyway
    ("<summary>48.0</summary><support>1</support>", set()),  # other tags that start with 'sup' or 'sum'
    ("<td>15,240</td><td>48.0<sup>1", set()),              # an unclosed tag
    ("no tags at all 48.01", set()),
    ("", set()), (None, set()),
])
def test_glued_marks_cases(mod, html, marks):
    assert mod._glued_marks(html) == marks


def test_glued_marks_bytes_and_cap(mod):
    assert mod._glued_marks(b"<td>48.0<sup>1</sup></td>") == {"48.01"}
    many = "".join(f"<td>{i}.5<sup>1</sup></td>" for i in range(mod.MAX_MARKS + 50))
    assert len(mod._glued_marks(many)) == mod.MAX_MARKS


TB = one("tb", "Total borrowings", decimals=0)


def test_a_figure_on_a_line_with_a_glued_mark_is_refused(env, mod):
    env.vm.warp(iso(E0 - 1800))
    env.vm.sender = env.alice
    s = env.c.register_report(json.dumps(live_spec(figs=TB)))["spec"]  # the frozen, canonical report
    text = head("All figures in EUR millions.") + "Total borrowings 48.01 47.12\n"
    a = json.loads(ans(TAR, {"tb": fig("48.01", "Total borrowings", "millions", "EUR millions")}).replace("```json", "").replace("```", ""))
    assert mod._interpret(s, 0, a, text)["kind"] == "READ"  # text alone cannot tell: the reason the HTML is read
    r = mod._interpret(s, 0, a, text, {"48.01", "47.12"})
    assert r == {"kind": "NO_READING", "reason": "N2_FORMAT"}
    assert mod._interpret(s, 0, a, text, {"15.01"})["kind"] == "READ"  # a mark on another line does not matter
    assert mod._interpret(s, 0, a, text, set())["kind"] == "READ"


def test_read_refuses_a_footnoted_value_end_to_end(env):
    # the direct runner gives the same body for the text and the HTML rendering, so the body carries both: the lines as Studio
    # prints them, and the row's HTML as one more line of text
    body = head("All figures in EUR millions.") + "Total borrowings 48.01 47.12\n<tr><td>Total borrowings</td><td>48.0<sup>1</sup></td><td>47.1<sup>2</sup></td></tr>\n"
    refused(run(env, live_spec(figs=TB), body, ans(TAR, {"tb": fig("48.01", "Total borrowings", "millions", "EUR millions")})), "N2_FORMAT")
    clean = head("All figures in EUR millions.") + "Total borrowings 48.01 47.12\n"
    read_ok(run(env, live_spec(figs=TB), clean, ans(TAR, {"tb": fig("48.01", "Total borrowings", "millions", "EUR millions")})), "tb", "48010000")


def test_marked(mod):
    assert mod._marked("total borrowings 48.01 47.12", {"48.01"}) is True
    assert mod._marked("total borrowings 148.01 47.12", {"48.01"}) is False  # whole tokens only
    assert mod._marked("total borrowings 48.01", None) is False and mod._marked("total borrowings 48.01", set()) is False


# ------------------------------------------- small items


@pytest.mark.parametrize("mark", ["(-)", "( - )", "•", "="])
def test_more_empty_cell_marks(env, mark):
    p = head("All figures in EUR thousands unless stated otherwise.") + f"Revenue {mark} 14,880\n"
    refused(run(env, live_spec(figs=REV), p, ans(TAR, {"revenue": fig("14,880", "Revenue", "thousands", "EUR thousands")})), "N2_NOT_ANCHORED")


def test_the_cut_keeps_the_last_whole_line_as_printed(mod):
    p = "x" * 11960 + "\nRevenue 15,240\n" + "y" * 100 + "\n"
    assert mod._clean_page(p).endswith("\nRevenue 15,240")
    p = "x" * 11960 + "\nRevenue 15 240\n" + "y" * 100 + "\n"
    assert mod._clean_page(p).endswith("\nRevenue 15 240")  # not made smaller


@pytest.mark.parametrize("line", ["Revenue for the year was EUR 16.2 million", "Revenue for the full year rose to EUR 16.2 million",
                                  "Revenue for the half year was EUR 16.2 million", "Revenue for the quarter was EUR 16.2 million"])
def test_for_the_year_links_a_label_to_its_value(env, line):
    p = page("euros (EUR)", line)
    read_ok(run(env, live_spec(figs=REV), p, ans(TAR, {"revenue": fig("EUR 16.2 million", "Revenue", "millions", "million")})), "revenue", "16200000")


@pytest.mark.parametrize("line", ["Revenue for the prior year was EUR 14.9 million", "Revenue for the year 2025 was EUR 14.9 million"])
def test_another_year_does_not_link(env, line):
    p = page("euros (EUR)", line)
    refused(run(env, live_spec(figs=REV), p, ans(TAR, {"revenue": fig("EUR 14.9 million", "Revenue", "millions", "million")})), "N2_NOT_ANCHORED")


@pytest.mark.parametrize("copy,code,ok", [("£m", "GBP", True), ("£000", "GBP", True), ("£'000", "GBP", True), ("€m", "EUR", True), ("€ million", "EUR", True),
                                          ("£", "GBP", True), ("£m", "EUR", False), ("£ per share", "GBP", False), ("£x", "GBP", False), ("$m", "USD", False)])
def test_the_currency_sign_with_a_scale(mod, copy, code, ok):
    assert mod._currency_matches(copy, code) is ok


def test_a_pound_million_page_reads(env):
    p = (f"{TAR}\nQuarterly results\nResults for the quarter ended 2026-11-18 08:15 UTC.\n£m Quarter ended 2026-11-18 08:15 UTC Prior quarter\nRevenue 16.2 14.9\n")
    r = run(env, live_spec(figs=REV, currency="GBP"), p, ans(TAR, {"revenue": fig("16.2", "Revenue", "millions", "£m")}, currency="£m"))
    read_ok(r, "revenue", "16200000")


def test_the_currency_prefix_of_a_copied_value(env):
    # was listed as an equivalent mutant; it is not: the reason code differs
    p = page("euros (EUR)", "Revenue 16.2 EURm 14.9 EURm")
    r = run(env, live_spec(figs=REV), p, ans(TAR, {"revenue": fig("16.2 EURm", "Revenue", "millions", "EURm")}))
    assert r["kind"] == "NO_READING" and r["reason"] == "N2_FORMAT", r


# ------------------------------------------- the ninth review's hand-made mutants that no test caught


def test_a_comma_does_not_start_a_phrase(mod):
    assert mod._starts_phrase("segment two, ebitda 2,390", 13) is False
    assert mod._starts_phrase("segment two; ebitda 2,390", 13) is True


def test_pence_three_rows_above_refuse(env):
    p = page("pounds sterling (GBP)", "\u00a3000", "pence pence", "Quarter ended 2026-11-18 08:15 UTC Prior quarter", "Revenue 15,240 14,880", "Interim dividend 4.5 4.2")
    figs = one("div", "Interim dividend", decimals=2)
    for scale, st in (("thousands", "\u00a3000"), ("units", "GBP")):
        refused(run(env, live_spec(figs=figs, currency="GBP"), p, ans(TAR, {"div": fig("4.5", "Interim dividend", scale, st)}, currency="GBP")), "N2_UNITS_MISSING")


def test_the_official_reading_keeps_its_own_period_url(env):
    from tests.direct.test_report_reader import ts
    register(env)
    end2 = ts(ENDS[2])
    page2 = PAGE.replace("2026-11-20 10:00", "2026-11-20 12:00").replace("15,240", "16,010")
    read(env, answer(figs={"revenue": {"value": "16,010"}}, period_end_on_page="2026-11-20 12:00 UTC"), n=2, at=end2 + LAG * 60, page=page2)
    g = env.c.get_reading("1", 2, end2 + LAG * 60 + 1)
    assert g["status"] == "READ" and g["url"] == URL_T.replace("{n}", "2")


def test_bare_a_digit_before_a_code_is_not_bare(mod):
    # mutation run v12: the digit side of the check before the phrase
    assert mod._bare_on_line("eps 1eur 0.45", "eur") is False
    assert mod._bare_on_line("eps 1 eur 0.45", "eur") is True
    assert mod._bare_on_line("eps 1€ 0.45", "€") is True  # a symbol may follow a digit
