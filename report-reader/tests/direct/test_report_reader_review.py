"""Regression tests for the weak points found by the independent review of
18 Nov 2026. Each test feeds the contract a page shaped like the live s1
pages (table cells as tabs, as the browser's text rendering gives them) and
checks that code now refuses the wrong copy, or still reads the right one.

Every company, page and figure here is fictional (Tarnwick Harbour Holdings
plc, Ostravelle Fibre SA).
"""

import json
import re

import pytest

from tests.direct.test_report_reader import env, mod, iso, END0, register as reg_default, read as read_default, answer as answer_default  # noqa: F401

E0 = 1794989700  # 2026-11-18 08:15 UTC
OPEN = E0 + 5 * 60
SITE = "https://reports.example/s1"
PROMPT = r"(?s).*periodic report.*"
TAR = "Tarnwick Harbour Holdings plc"
OST = "Ostravelle Fibre SA"

BASE_FIGS = [
    {"key": "revenue", "label_hint": "Revenue for the quarter", "labels": ["Revenue"], "ltm": False, "decimals": 0, "step": 1000, "rounding": "down", "sign": "as_printed"},
    {"key": "ltm_ebitda", "label_hint": "EBITDA for the last twelve months", "labels": ["EBITDA (last twelve months)", "LTM EBITDA"], "ltm": True, "decimals": 0, "step": 1000, "rounding": "down", "sign": "as_printed"},
    {"key": "net_finance_costs", "label_hint": "Net finance costs (net interest expense)", "labels": ["Net finance costs"], "ltm": False, "decimals": 0, "step": 1000, "rounding": "up", "sign": "finance_cost"},
    {"key": "total_debt", "label_hint": "Total borrowings", "labels": ["Total borrowings"], "ltm": False, "decimals": 0, "step": 1000, "rounding": "up", "sign": "magnitude"},
]


def table_page(issuer, end="2026-11-18 08:15 UTC", ebitda_label="EBITDA (last twelve months)", rows=None, heading="All figures in EUR thousands unless stated otherwise.", extra=""):
    rows = rows or [("Revenue", "15,240", "14,880"), (ebitda_label, "4,180.5", "3,960.0"), ("Net finance costs", "(2,150)", "(2,040)"), ("Total borrowings", "(48,000)", "(49,500)")]
    body = "".join(f"\n\t{a}\t{b}\t{c}\n" for a, b, c in rows)
    return (f"\n\n{issuer}\nQuarterly results\n\nResults for the quarter ended {end}.\n{heading}\n\n\n"
            f"\t\tQuarter ended {end}\tPrior quarter\n{body}\n{extra}\nFictional company and figures. Not investment information.\n")


TARNWICK = table_page(TAR)
# Studio's render of the s2 table page, as the RenderProbe contract returned it (cells joined by one space)
TARNWICK_RENDERED = ("Tarnwick Harbour Holdings plc\nQuarterly results\n\nResults for the quarter ended 2026-11-18 08:15 UTC.\n\n"
                     "All figures in EUR thousands unless stated otherwise.\n\nQuarter ended 2026-11-18 08:15 UTC Prior quarter ended 2026-08-19 08:15 UTC\n"
                     "Revenue 15,240 14,880\nEBITDA (last twelve months) 4,180.5 3,960.0\nNet finance costs (2,150) (2,040)\nTotal borrowings (48,000) (49,500)\n\n"
                     "The board approved these results for publication. Net finance costs are shown in brackets as an expense.\n\n"
                     "Fictional company and figures, published for a GenLayer ReportReader demonstration by Brilliant Nodes. Not investment information.")
OST_ROWS = [("Revenue", "8,315", "8,020"), ("EBITDA (last twelve months)", "2,240.0", "2,105.5"), ("Net finance costs", "(910)", "(955)"), ("Total borrowings", "(21,400)", "(21,900)")]
OSTRAVELLE = table_page(OST, rows=OST_ROWS)
OST_ADJUSTED = table_page(OST, rows=[OST_ROWS[0], ("Adjusted EBITDA (last twelve months)", "2,390.0", "2,250.5")] + OST_ROWS[2:], extra="Adjusted EBITDA excludes restructuring costs.\n")
OST_OLD = table_page(OST, end="2026-08-19 08:15 UTC", rows=OST_ROWS)
HIGHLIGHTS = (f"{TAR}\nQuarterly highlights\nHighlights for the quarter ended 2026-11-18 08:45 UTC. All amounts in euros (EUR).\n"
              "Revenue: EUR 16.2 million\nLTM EBITDA: EUR 4.45 million\nNet finance costs: EUR 2.1 million\nTotal borrowings: EUR 47.5 million\n"
              "LTM means the last twelve months to the quarter end.\n")


def live_spec(issuer=TAR, figs=None, currency="EUR", end="2026-11-18 08:15"):
    return {"issuer_name": issuer, "url_template": f"{SITE}/x/q-{{n}}.html", "currency": currency,
            "period_ends": [end], "publish_lag_minutes": 5, "read_window_minutes": 30, "figures": figs or BASE_FIGS}


def fig(value, label, scale="thousands", scale_text="EUR thousands", ltm="no"):
    return {"value": value, "scale": scale, "scale_text": scale_text, "ltm_labelled": ltm, "conflicting": "no", "line_label": label}


def ans(issuer, figures, period="2026-11-18 08:15 UTC", currency="EUR"):
    return "```json\n" + json.dumps({"page_kind": "periodic_report", "issuer_name_on_page": issuer, "period_end_on_page": period,
                                      "currency_on_page": currency, "marked_draft": "no", "decimal_mark": ".", "figures": figures}) + "\n```"


def run(e, spec, page, llm, end=E0):
    e.vm.warp(iso(E0 - 1800))
    e.vm.sender = e.alice
    rid = e.c.register_report(json.dumps(spec))["id"]
    e.vm.clear_mocks()
    e.vm.warp(iso(end + 5 * 60 + 60))
    e.vm.sender = e.bob
    e.vm.mock_web(re.escape(f"{SITE}/x/q-0.html"), {"status": 200, "body": page})
    e.vm.mock_llm(PROMPT, llm)
    return e.c.read(rid, 0)


def refused(r, reason):
    assert r["kind"] == "NO_READING" and r["reason"] == reason, r


T_FIGS = {"revenue": fig("15,240", "Revenue"), "ltm_ebitda": fig("4,180.5", "EBITDA (last twelve months)", ltm="yes"),
          "net_finance_costs": fig("(2,150)", "Net finance costs"), "total_debt": fig("(48,000)", "Total borrowings")}
O_FIGS = {"revenue": fig("8,315", "Revenue"), "ltm_ebitda": fig("2,240.0", "EBITDA (last twelve months)", ltm="yes"),
          "net_finance_costs": fig("(910)", "Net finance costs"), "total_debt": fig("(21,400)", "Total borrowings")}
OP_FIGS = [{"key": "operating_profit", "label_hint": "Operating profit or loss", "labels": ["Operating profit/(loss)"], "rounding": "down", "sign": "as_printed"}]


# ------------------------------------------------ pages that must still read


def test_table_page_reads(env):
    r = run(env, live_spec(), TARNWICK, ans(TAR, T_FIGS))
    assert r["kind"] == "READ" and r["figures"] == {"revenue": "15240000", "ltm_ebitda": "4180000", "net_finance_costs": "2150000", "total_debt": "48000000"}, r
    assert env.vm.run_validator() is True


def test_rendered_table_page_reads_and_refuses_the_prior_column(env):
    r = run(env, live_spec(), TARNWICK_RENDERED, ans(TAR, T_FIGS))
    assert r["kind"] == "READ" and r["figures"] == {"revenue": "15240000", "ltm_ebitda": "4180000", "net_finance_costs": "2150000", "total_debt": "48000000"}, r
    refused(run(env, live_spec(), TARNWICK_RENDERED, ans(TAR, {**T_FIGS, "revenue": fig("14,880", "Revenue")})), "N2_NOT_ANCHORED")


def test_highlights_page_reads(env):
    figs = {"revenue": fig("EUR 16.2 million", "Revenue", "millions", "million"), "ltm_ebitda": fig("EUR 4.45 million", "LTM EBITDA", "millions", "million", ltm="yes"),
            "net_finance_costs": fig("EUR 2.1 million", "Net finance costs", "millions", "million"), "total_debt": fig("EUR 47.5 million", "Total borrowings", "millions", "million")}
    end = E0 + 30 * 60
    r = run(env, live_spec(end="2026-11-18 08:45"), HIGHLIGHTS, ans(TAR, figs, period="2026-11-18 08:45 UTC"), end=end)
    assert r["kind"] == "READ" and r["figures"] == {"revenue": "16200000", "ltm_ebitda": "4450000", "net_finance_costs": "2100000", "total_debt": "47500000"}, r


def test_pound_000_heading_reads_as_thousands(env):
    page = TARNWICK.replace("EUR thousands", "£000")
    good = {k: {**v, "scale_text": "£000"} for k, v in T_FIGS.items()}
    r = run(env, live_spec(currency="GBP"), page, ans(TAR, good, currency="GBP"))
    assert r["kind"] == "READ" and r["figures"]["revenue"] == "15240000", r


def test_own_symbol_alone_is_the_currency(env, mod):
    assert mod._currency_matches("€", "EUR") and mod._currency_matches("£", "GBP")
    assert not mod._currency_matches("$", "USD")  # $ is shared by many currencies


def test_note_references_are_not_amounts_or_decimal_commas(env, mod):
    assert not mod._decimal_comma_page("Revenue (notes 3,4) 15,240")
    assert not mod._decimal_comma_page("Revenue (note 4.2 and 7) 15,240")
    assert mod._decimal_comma_page("Revenue (note 3) 12,5")
    page = TARNWICK.replace("\tRevenue\t15,240", "\tRevenue (note 4)\t15,240")
    r = run(env, live_spec(), page, ans(TAR, T_FIGS))
    assert r["kind"] == "READ" and r["figures"]["revenue"] == "15240000", r


# ------------------------------------------------------- B1: label anchoring


def test_adjusted_label_is_not_the_listed_label(env):
    figs = {**O_FIGS, "ltm_ebitda": fig("2,390.0", "EBITDA (last twelve months)", ltm="yes")}
    refused(run(env, live_spec(OST), OST_ADJUSTED, ans(OST, figs)), "N2_NOT_ANCHORED")
    assert env.vm.run_validator() is True  # validators agree on the refusal


def test_value_from_the_next_row_is_not_anchored(env):
    refused(run(env, live_spec(), TARNWICK, ans(TAR, {**T_FIGS, "revenue": fig("4,180.5", "Revenue")})), "N2_NOT_ANCHORED")


def test_value_from_the_prior_column_is_not_anchored(env):
    refused(run(env, live_spec(), TARNWICK, ans(TAR, {**T_FIGS, "revenue": fig("14,880", "Revenue")})), "N2_NOT_ANCHORED")


@pytest.mark.parametrize("line", [
    "Revenue per employee 120",
    "Revenue from services 120",
    "Non-recurring revenue 120",
    "Segment revenue 120",
    "Revenue for the nine months 120",
    "Revenue 2026 120",
    "Revenue 7 120",
])
def test_other_words_or_numbers_before_the_value_refuse(env, mod, line):
    assert mod._anchored(mod._page_lines(line), "revenue", "120", "EUR") is None


@pytest.mark.parametrize("line,value", [
    ("Revenue 120", "120"),
    ("Revenue 15,240 880", "15,240"),  # the browser's text: one space between table cells
    ("Revenue (2,150) (2,040)", "(2,150)"),
    ("| Revenue | 120 | 110", "120"),
    ("- Revenue: 120", "120"),
    ("1. Revenue: 120", "120"),
    ("Revenue for the quarter rose 9% to EUR 120 thousand", "EUR 120 thousand"),
    ("Revenue (note 4) 120", "120"),
    ("Highlights: Revenue was EUR 120 million", "EUR 120 million"),
])
def test_label_then_value_anchors(env, mod, line, value):
    assert mod._anchored(mod._page_lines(line), "revenue", value, "EUR") is not None


@pytest.mark.parametrize("line,value", [
    ("revenue growth 12% to 15,240", "12"),
    ("revenue (2026-11-18) 15,240", "2026"),
    ("revenue 40'000", "40"),
    ("revenue 15 240", "15"),
    ("revenue 915 880", "915"),  # two cells or one space-grouped number: refused
    ("revenue 15,240.5", "15,240"),
    ("revenue 2/3", "2"),
])
def test_part_of_a_number_is_not_anchored(env, mod, line, value):
    assert mod._anchored(mod._page_lines(line), "revenue", value, "EUR") is None


# ---------------------------------------------------------- B2: the scale


def test_one_letter_scale_text_does_not_pass(env):
    figs = {**T_FIGS, "revenue": fig("15,240", "Revenue", scale="millions", scale_text="m")}
    refused(run(env, live_spec(), TARNWICK, ans(TAR, figs)), "N2_UNITS_MISSING")


def test_units_under_a_thousands_heading_refuse(env):
    figs = {**T_FIGS, "revenue": fig("15,240", "Revenue", scale="units", scale_text="EUR")}
    refused(run(env, live_spec(), TARNWICK, ans(TAR, figs)), "N2_UNITS_MISSING")


def test_line_scale_beats_the_heading(env):
    page = TARNWICK.replace("Total borrowings\t(48,000)\t(49,500)", "Total borrowings (EUR million)\t48.0\t49.5")
    figs = {**T_FIGS, "total_debt": fig("48.0", "Total borrowings")}
    refused(run(env, live_spec(), page, ans(TAR, figs)), "N2_UNITS_MISSING")  # the heading's thousands is not this line's scale
    good = {"total_debt": fig("48.0", "Total borrowings", "millions", "EUR million")}
    r = run(env, live_spec(figs=[BASE_FIGS[3]]), page, ans(TAR, good))
    assert r["kind"] == "READ" and r["figures"]["total_debt"] == "48000000", r
    # the page's headings now name two scales, so a figure whose own line names none is refused, not guessed
    refused(run(env, live_spec(), page, ans(TAR, {**T_FIGS, "total_debt": good["total_debt"]})), "N2_UNITS_MISSING")


def test_pound_000_heading_read_as_units_refuses(env):
    page = TARNWICK.replace("EUR thousands", "£000")
    wrong = {k: {**v, "scale": "units", "scale_text": "£000"} for k, v in T_FIGS.items()}
    refused(run(env, live_spec(currency="GBP"), page, ans(TAR, wrong, currency="GBP")), "N2_UNITS_MISSING")


# ----------------------------------------------------------- B3: the sign


def test_brackets_dropped_refuse(env):
    page = TARNWICK.replace("\tRevenue\t15,240\t14,880", "\tOperating profit/(loss)\t(1,200)\t900")
    refused(run(env, live_spec(figs=OP_FIGS), page, ans(TAR, {"operating_profit": fig("1,200", "Operating profit/(loss)")})), "N2_NOT_ANCHORED")
    r = run(env, live_spec(figs=OP_FIGS), page, ans(TAR, {"operating_profit": fig("(1,200)", "Operating profit/(loss)")}))
    assert r["kind"] == "READ" and r["figures"]["operating_profit"] == "-1200000", r


def test_minus_dropped_refuses_and_en_dash_minus_reads(env):
    page = TARNWICK.replace("\tRevenue\t15,240\t14,880", "\tOperating profit/(loss)\t–1,200\t900")
    refused(run(env, live_spec(figs=OP_FIGS), page, ans(TAR, {"operating_profit": fig("1,200", "Operating profit/(loss)")})), "N2_NOT_ANCHORED")
    r = run(env, live_spec(figs=OP_FIGS), page, ans(TAR, {"operating_profit": fig("–1,200", "Operating profit/(loss)")}))
    assert r["kind"] == "READ" and r["figures"]["operating_profit"] == "-1200000", r


# ----------------------------------------- B4: issuer, period, currency on the page


def test_previous_quarter_page_refuses_whatever_the_model_writes(env):
    refused(run(env, live_spec(OST), OST_OLD, ans(OST, O_FIGS)), "N2_WRONG_PERIOD")


def test_another_companys_page_refuses_whatever_the_model_writes(env):
    refused(run(env, live_spec(OST), TARNWICK, ans(OST, T_FIGS)), "N1_WRONG_PAGE")


def test_currency_must_be_printed_on_the_page(env):
    figs = {k: {**v, "scale_text": "thousands"} for k, v in T_FIGS.items()}
    refused(run(env, live_spec(currency="USD"), TARNWICK, ans(TAR, figs, currency="USD")), "N2_CURRENCY")


@pytest.mark.parametrize("printed,ok", [
    ("2026-11-18 08:15 UTC", True),
    ("2026-11-18T08:15Z", True),
    ("2026-11-18", False),  # a day only names a midnight end
    ("2026-11-18 08:16 UTC", False),
    ("2026-11-18 08:15:30 UTC", False),
    ("2026-11-18 08:15:00 UTC", True),
    ("2026-11-18 08:150", False),
])
def test_period_end_printed(env, mod, printed, ok):
    assert mod._period_on_page(mod._page_lines(f"Results for the quarter ended {printed}"), E0) is ok


@pytest.mark.parametrize("printed", ["2026-12-31", "31 December 2026", "December 31, 2026"])
def test_midnight_end_printed_as_its_last_day(env, mod, printed):
    from datetime import datetime, timezone
    end = int(datetime(2027, 1, 1, tzinfo=timezone.utc).timestamp())
    assert mod._period_on_page(mod._page_lines(f"Results for the year ended {printed}"), end)
    assert not mod._period_on_page(mod._page_lines("Results for the year ended 2026-12-30"), end)


# ------------------------------------------------------------- should-fix


def test_page_cut_never_ends_inside_a_number(env, mod):
    head = f"{TAR}\nResults for the quarter ended 2026-11-18 08:15 UTC.\nAll figures in EUR thousands.\n"
    tail = "Revenue\t1,524"
    page = head + "x" * (mod.PAGE_CHARS - len(head) - len(tail)) + tail + ",000\t1,498,000\n"
    cut = mod._clean_page(page)
    assert "Revenue" not in cut and len(cut) < mod.PAGE_CHARS  # the cut line is dropped whole
    refused(run(env, live_spec(figs=[BASE_FIGS[0]]), page, ans(TAR, {"revenue": fig("1,524", "Revenue")})), "N2_NOT_ANCHORED")


def test_reading_seen_before_the_period_end_is_flagged(env):
    reg_default(env)
    read_default(env, answer_default())
    g = env.c.get_reading("1", 0, END0 - 1)
    assert g["status"] == "NOT_DUE" and g["has_official"] is True and g["clock"] >= g["end_ts"], g


@pytest.mark.parametrize("url", [
    "https://127.0.0.1.nip.io/q-0.html",
    "https://app.10.0.0.1.sslip.io/q-0.html",
    "https://localtest.me/q-0.html",
    "https://10-0-0-1.reports.example/q-0.html",
    "https://192.168.1.1.reports.example/q-0.html",
    "http://reports.example/q-0.html",
])
def test_addresses_inside_names_are_refused(env, mod, url):
    assert mod._url_problem(url) != ""


def test_label_order_does_not_change_the_digest(env):
    a = live_spec()
    b = json.loads(json.dumps(a))
    b["figures"][1]["labels"] = list(reversed(b["figures"][1]["labels"]))
    env.vm.warp(iso(E0 - 1800))
    env.vm.sender = env.alice
    assert env.c.register_report(json.dumps(a))["digest"] == env.c.register_report(json.dumps(b))["digest"]


# ------------------------------------------- gaps the mutation run found (v2)


@pytest.mark.parametrize("url", ["https://169.254.1.1/q-{n}.html", "https://reports.internal/q-{n}.html"])
def test_link_local_and_internal_hosts_are_refused(env, url):
    env.vm.warp(iso(E0 - 1800))
    env.vm.sender = env.alice
    with pytest.raises(Exception, match="public address"):
        env.c.register_report(json.dumps({**live_spec(), "url_template": url}))


def test_issuer_of_two_letters_is_refused(env):
    env.vm.warp(iso(E0 - 1800))
    env.vm.sender = env.alice
    with pytest.raises(Exception, match="at least 3 letters"):
        env.c.register_report(json.dumps(live_spec(issuer="AB")))


def test_issuer_copied_inside_a_longer_name_refuses(env):
    refused(run(env, live_spec(), TARNWICK, ans(TAR + "s", T_FIGS)), "N1_WRONG_PAGE")


def test_foreign_symbol_in_the_copied_currency_refuses(env):
    refused(run(env, live_spec(), TARNWICK, ans(TAR, T_FIGS, currency="EUR ($)")), "N2_CURRENCY")


@pytest.mark.parametrize("line,label,value", [
    ("Revenue" + " |" * 100 + " 15,240", "revenue", "15,240"),  # beyond ANCHOR_CHARS
    ("Revenuem 15", "revenue", "15"),  # the label runs on into another word
    ("Pre-tax profit 1,200", "tax profit", "1,200"),  # an unspaced dash joins words
    ("U.S. revenue 120", "revenue", "120"),  # not a list number
    ("Revenue έσοδα 120", "revenue", "120"),  # letters this code cannot judge
    ("Revenue .5", "revenue", "5"),  # part of '.5'
    ("Revenue 1,200)", "revenue", "1,200"),  # a closing bracket the copy does not carry
    ("Revenue note 4/5 120", "revenue", "5"),  # part of '4/5'
    ("Revenue note 4/5", "revenue", "5"),
    ("Revenue note 4:5", "revenue", "5"),
])
def test_more_lines_that_do_not_anchor(env, mod, line, label, value):
    assert mod._anchored(mod._page_lines(line), label, value, "EUR") is None


def scale_ok(mod, page, line, scale_text, mult, code="EUR"):
    return mod._scale_ok(mod._page_lines(page), mod._norm(line), scale_text, mult, code)


def test_scale_text_must_be_whole_words(env, mod):
    assert not scale_ok(mod, "All amounts in euros\nRevenue 15,240", "Revenue 15,240", "eur", 1)
    assert mod._phrase_on_page("in eur million", "million") and mod._phrase_on_page("(eur)", "(eur)")
    assert not mod._phrase_on_page("in xmillion", "million") and not mod._phrase_on_page("in millions", "million")


def test_units_copy_may_not_name_a_scale(env, mod):
    page = f"{TAR}\nRevenue 15,240\nThe bond of EUR 2.5 million was repaid"
    assert not scale_ok(mod, page, "Revenue 15,240", "million", 1)


def test_scale_text_naming_two_scales_refuses(env, mod):
    page = "Figures in thousands; bond 48.0 million\nRevenue 15,240"
    assert not scale_ok(mod, page, "Revenue 15,240", "thousands; bond 48.0 million", 10**3)
    assert scale_ok(mod, page, "Revenue 15,240", "thousands", 10**3)


@pytest.mark.parametrize("text", ["Total 1.234,567", "Total 1.234.567"])
def test_more_decimal_comma_pages(env, mod, text):
    assert mod._decimal_comma_page(text)


def test_stored_figure_above_the_cap_refuses(env):
    figs = [{"key": "nav", "label_hint": "Net asset value", "labels": ["Net asset value"], "decimals": 6, "step": 1, "rounding": "down", "sign": "as_printed"}]
    big = "9,999,999,999,999,999,999,999,999"  # 25 digits: under the copy cap, over the stored cap with 6 decimals
    page = TARNWICK.replace("\tRevenue\t15,240\t14,880", f"\tNet asset value\t{big}\t1")
    refused(run(env, live_spec(figs=figs), page, ans(TAR, {"nav": fig(big, "Net asset value")})), "N2_FORMAT")
