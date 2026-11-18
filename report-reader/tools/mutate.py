#!/usr/bin/env python3
"""Mutation check: break each contract on purpose, one change at a time, and
confirm that the direct-mode tests catch every break.

    cd report-reader && PYTHONPATH=. ../venv/bin/python tools/mutate.py [reader|earnout]

Each mutant is written to a temporary file and the tests are pointed at it
with RR_CONTRACT or EO_CONTRACT; the contracts themselves are never modified.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

READER = [
    # one official reading, windows and the clock
    ("official reading can be replaced", 'if p["official"] is not None:\n            raise gl.vm.UserError(f"period {n} already has', 'if False:\n            raise gl.vm.UserError(f"period {n} already has'),
    ("any outcome becomes official", 'if outcome["kind"] == "READ":\n            p["official"]', 'if True:\n            p["official"]'),
    ("not-published becomes official", 'if outcome["kind"] == "READ":\n            p["official"]', 'if outcome["kind"] in ("READ", "NOT_PUBLISHED"):\n            p["official"]'),
    ("read before the window opens", "if now < _opens(spec, n):\n            raise", "if now < _ends(spec)[n]:\n            raise"),
    ("read after the window closes", "if now >= _closes(spec, n):\n            return", "if False:\n            return"),
    ('clock runs backwards', 'now = max(old, self._tx_time())', 'now = self._tx_time()'),
    ("publishing lag ignored", 'return _ends(spec)[n] + spec["publish_lag_minutes"] * 60', "return _ends(spec)[n]"),
    ("MISSING before the close is settled", 'return "MISSING" if clock >= _closes(spec, n) else "CLOSING"', 'return "MISSING"'),
    ("READ shown before it happened", 'if off is not None and off["at"] <= at:', "if off is not None:"),
    ("no WAITING status", 'if at < _opens(spec, n):\n        return "WAITING"', 'if False:\n        return "WAITING"'),
    ("tick lists periods that were read", 'if now >= _closes(spec, n) and self._period(report_id, n)["official"] is None]', "if now >= _closes(spec, n)]"),
    ("each period reads page 0", 'return spec["url_template"].replace("{n}", str(n))', 'return spec["url_template"].replace("{n}", "0")'),
    ("attempts unbounded", 'if len(p["attempts"]) < MAX_ATTEMPTS_KEPT:', "if True:"),
    ("attempts not counted", 'p["attempt_count"] += 1', "pass"),
    # the specification
    ("window may be one minute", "MIN_WINDOW_MINUTES = 30  #", "MIN_WINDOW_MINUTES = 1  #"),
    ("nine figures", "MAX_FIGURES = 8", "MAX_FIGURES = 9"),
    ("25 periods", "MAX_PERIODS = 24", "MAX_PERIODS = 25"),
    ("period ends may repeat", "if ends and ts <= ends[-1]:", "if ends and ts < ends[-1]:"),
    ("no five-year limit", "if ends[-1] > now + MAX_AHEAD_SECONDS:", "if False:"),
    ("unknown field allowed", "extra = [k for k in spec.keys() if k not in SPEC_KEYS]", "extra = []"),
    ("unknown figure field allowed", "extra = [k for k in f.keys() if k not in FIGURE_KEYS]", "extra = []"),
    ("duplicate figure keys", "if key in seen:", "if False:"),
    ("step need not be a power of ten", ' or s.rstrip("0") != "1"', ""),
    ("{n} twice", 'if tpl.count("{n}") != 1 or', 'if tpl.count("{n}") < 1 or'),
    ("{n} in the host", 'if "/" not in after_scheme or after_scheme.index("{n}") < after_scheme.index("/"):', "if False:"),
    ("query allowed", 'if "?" in tpl or "#" in tpl:', 'if "#" in tpl:'),
    ("private hosts allowed", "if _is_private_host(_host_of(url)):", "if False:"),
    ("http allowed", 'if not url.startswith("https://"):', 'if not url.startswith(("https://", "http://")):'),
    ("wildcard DNS allowed", 'if any(host == w or host.endswith("." + w) for w in WILDCARD_DNS):', "if False:"),
    ("address inside a name allowed", "if any(all(c in DIGITS for c in lab) for lab in labels[:-1]):", "if False:"),
    ("dashed address allowed", 'if any(lab.count("-") >= 3 and all(c in DIGITS or c == "-" for c in lab) for lab in labels):', "if False:"),
    ("link-local 169.254 allowed", "(a == 169 and b == 254)", "False"),
    ("internal suffixes allowed", "if host.endswith(PRIVATE_SUFFIXES):", "if False:"),
    ("one-letter labels", "if len(nl) < 3 or sum(1 for c in nl if c.isalpha()) < 2:", "if not any(c.isalpha() for c in nl):"),
    ("label order changes the digest", "    clean.sort()  #", "    pass  #"),
    ("markup in hints", "if any(not (c.isalnum() or c in HINT_CHARS) for c in hint):", "if False:"),
    ("issuer of one letter", "if sum(1 for c in name if c.isalpha()) < 3:", "if not any(c.isalnum() for c in name):"),
    ("labels not normalised", "nl = _norm_label(lab)", "nl = lab"),
    ("trailing colon kept", 'while s.endswith(":"):', "while False:"),
    ("digest over the raw input", "digest=_digest(spec)", 'digest=_digest({"raw": spec_json})'),
    # interpreting the copy
    ("issuer not whole words", 'f" {name} " not in f" {on_page} "', "name not in on_page"),
    ("issuer not checked", 'or f" {name} " not in f" {on_page} " or', "or"),
    ("issuer not on the page", ' or f" {name} " not in f" {_name_words(page)} ":', ":"),
    ("draft accepted", 'if _yes(ans.get("marked_draft")):', "if False:"),
    ("period not checked", 'if not _period_matches(ans.get("period_end_on_page"), end) or', "if"),
    ('period not on the page', ' or not _period_on_page(lines, end, _ends(spec)[n + 1:]):', ':'),
    ("seconds after the minute ignored", 'ok = ok and tail.startswith(":00") and not tail[3:4].isdigit()', "ok = ok"),
    ('period end minute ignored on the page', '                    if tail[:1].isalnum():\n                        ok = False\n                    t2 = tail.lstrip()', '                    t2 = tail.lstrip()'),
    ('another time zone accepted', '                    if t2[:k] not in UTC_ZONES:\n                        ok = False', '                    if False:\n                        ok = False'),
    ('comparative line accepted', 'if not _has_word(line[:i], PRIOR_WORDS) and not _date_before(line, i):', 'if not _date_before(line, i):'),
    ('midnight end: any day', 'last = datetime.fromtimestamp(end_ts - 1, timezone.utc)\n        y, dd', 'last = datetime.fromtimestamp(end_ts - 86401, timezone.utc)\n        y, dd'),
    ("currency not checked", 'if not _currency_matches(ans.get("currency_on_page"), spec["currency"]) or', "if"),
    ("currency not on the page", ' or not _currency_on_page(page_n, spec["currency"]):', ":"),
    ("own symbol not unique", 'UNIQUE_SYMBOLS = {"EUR": "\\u20ac", "GBP": "\\u00a3"}', 'UNIQUE_SYMBOLS = {"EUR": "\\u20ac", "GBP": "\\u00a3", "USD": "$"}'),
    ("foreign symbol in currency text allowed", "if any(sym in raw and sym != own for sym in SYMBOLS):", "if False:"),
    ("decimal comma mark accepted", 'not in (".", "none"):', 'not in (".", "none", ","):'),
    ("decimal-comma page accepted", 'if _decimal_comma_page(page):\n        return {"kind": "NO_READING", "reason": "N2_FORMAT"}', 'if False:\n        return {"kind": "NO_READING", "reason": "N2_FORMAT"}'),
    ("conflict ignored", 'if _yes(f.get("conflicting")):', "if False:"),
    ("LTM ignored", 'if fs["ltm"] and not _yes(f.get("ltm_labelled")):', "if False:"),
    ("closed label list ignored", 'if label_n not in fs["labels"]:', "if False:"),
    # anchored copying
    ('anchoring off', '        if anchor is None:\n            return {"kind": "NO_READING", "reason": "N2_NOT_ANCHORED"}\n        line, at = anchor', '        anchor = anchor or (lines[0] if lines else "", 0)\n        line, at = anchor'),
    ("anchor ten times further", "ANCHOR_CHARS = 160  #", "ANCHOR_CHARS = 1600  #"),
    ("lines flattened", '        out.append(_norm(line.replace("\\t", " | ")))\n    return out', "        out.append(_norm(line.replace(\"\\t\", \" | \")))\n    return [\" \".join(out)]"),
    ("label may start mid-phrase", "if _starts_phrase(line, i) and", "if True and"),
    ("label may end mid-word", "(b == len(line) or not line[b].isalnum() or not label_n[-1].isalnum())", "True"),
    ('any word before the label', "    if lead[-1] in LIST_MARKS:\n        return not _qualifier_before(lead[:-1])  # not 'Adjusted: EBITDA', 'Adjusted* EBITDA', 'Guidance | EBITDA'", "    if True:\n        return True  # not 'Adjusted: EBITDA', 'Adjusted* EBITDA', 'Guidance | EBITDA'"),
    ("unspaced dash starts a phrase", 'if lead[-1] == "-" and a > 0 and line[a - 1] == " " and (len(lead) == 1 or lead[-2] == " "):', 'if lead[-1] == "-":'),
    ('any word ending in a dot is a list number', 'and len(word) <= 4 and number and', 'and len(word) <= 4 and word[:-1].isalnum() and'),
    ('anything between label and value', ' and _between_ok(btw, code) and', ' and'),
    ("other words between label and value", "if w not in LINK_WORDS and w not in cur and w not in scale:", "if False:"),
    ("other numbers between label and value", 'if k >= n or s[k] != "%":\n                return False', 'if False:\n                return False'),
    ("unknown letters between label and value", "elif ch.isalpha():\n            return False", "elif False:\n            return False"),
    ("note references not dropped in between", "    s = _drop_note_refs(s)\n    for c in", "    for c in"),
    ("footnote letters not dropped", '        s = s.replace(f"({c})", " ")', "        pass"),
    ("another currency's amount first", "        return False  # an amount in another currency stands first", "        pass  # an amount in another currency stands first"),
    ('empty dash cell read as the next column', '    if toks and toks[-1] in ("-", "|-", "-|", "\\u2026", "...", "..", "*", ".", "|*", "|.", "\\u2022", "=", "(-)") or "".join(s.split()).endswith("(-)"):\n        return False', '    if False:\n        return False'),
    ("a change read as the figure", "    return last not in CHANGE_WORDS  #", "    return True  #"),
    ("sign before the currency dropped", "    if code and not value_n.startswith((\"(\", \"-\")) and _sign_across_currency(line, a, code):\n        return False", "    pass"),
    ("spaced dash read as a minus", '        if s[1:2] == " ":\n            return None  # a spaced dash', '        if False:\n            return None  # a spaced dash'),
    ("em dash not a minus", 'MINUS_GLYPHS = ("\\u2212", "\\u2013", "\\u2012", "\\u2014",', 'MINUS_GLYPHS = ("\\u2212", "\\u2013", "\\u2012",'),
    ("value edges ignored", "if _value_edges_ok(line, b + j, b + j + len(value_n), value_n, code) and", "if True and"),
    ("trailing digit or percent ignored", 'if after and (after.isalnum() or after == "%"):', "if False:"),
    ("trailing decimals ignored", 'if after in (".", ",", "\'", "-", "/", ":") and after2 != "" and after2 in DIGITS:', "if False:"),
    ("closing bracket ignored", 'if after == ")" and not value_n.endswith(")"):', "if False:"),
    ("space-grouped numbers split", 'and line[b + 1: b + 4].isdigit() and len(line[b + 1: b + 4]) == 3', "and False"),
    ("date part anchored", 'if before in ("/", ":") and before2 != "" and before2 in DIGITS:', "if False:"),
    ("value without digits anchored", " or not any(c in DIGITS for c in value_n)", ""),
    # scale
    ('scale words not checked', 'if mult is None or not _scale_ok(lines, line, f.get("scale_text"), mult, spec["currency"], value, fs["per_share"] is True, at, label_n):', 'if mult is None:'),
    ("the value's own scale ignored", 'f.get("scale_text"), mult, spec["currency"], value, fs["per_share"] is True, at, label_n)', 'f.get("scale_text"), mult, spec["currency"], None, fs["per_share"] is True, at, label_n)'),
    ("the word after the value ignored", "            found |= {m for m, words in SCALE_WORDS.items() if nxt in words}", "            pass"),
    ('per-share figures take the heading scale', 'spec["currency"], value, fs["per_share"] is True, at, label_n)', 'spec["currency"], value, False, at, label_n)'),
    ('per-share units without words on the line', 'st in cur and _bare_on_line(line, st)', 'st in cur'),
    ('one-letter scales count anywhere', '                    if tok in SINGLE_SCALES:\n                        if (after_currency or before_currency) and not area_or_class:', '                    if tok in SINGLE_SCALES:\n                        if True:'),
    ('scale words count without the currency', 'elif near_currency(i, j) or (prev_word == ["in"] and not of_noun) or after_currency or plural_alone:', 'else:'),
    ('LTM need not be printed', '        if fs["ltm"] and not any(_phrase_on_page(line[:at], w) for w in LTM_WORDS):', '        if False:'),
    ('page cut inside a line', '        text = text[:text.rindex("\\n")] if "\\n" in text else ""  # never split a line: no number is cut in two or loses its scale word', '        pass'),
    ("page_urls ignored", '    if "page_urls" in spec:\n        return spec["page_urls"][n]', '    if "page_urls" in spec:\n        return spec["page_urls"][0]'),
    ("page_urls count not checked", ' or len(urls) != len(ends) or', " or"),
    ("both url forms accepted", "    if (tpl is None) == (urls is None):", "    if tpl is None and urls is None:"),
    (".localdomain allowed", '".localhost", ".localdomain", ".local"', '".localhost", ".local"'),
    ("rebinding services allowed", '"1u.ms", "rbndr.us",', ""),
    ("line scale ignored", "if on_line:\n        return on_line == {mult}", "if False:\n        return on_line == {mult}"),
    ("line scale need not match", "return on_line == {mult}", "return mult in on_line or mult == 1"),
    ("scale words need not be printed", 'if st == "" or not any(_phrase_on_page(x, st) for x in lines):', 'if st == "":'),
    ('scale words may be part of a word', '    i = text_n.find(phrase_n)\n    while i >= 0:\n        a, b = i, i + len(phrase_n)\n        if (a == 0 or not text_n[a - 1].isalnum() or not phrase_n[0].isalnum()) and', '    i = text_n.find(phrase_n)\n    while i >= 0:\n        a, b = i, i + len(phrase_n)\n        if True and'),
    ('per-share copy need not be the currency', '        return mult == 1 and not own and st in cur and', '        return mult == 1 and not own and'),
    ("heading scale not required", "return named == {mult} and _page_scales(lines, code) == {mult}", "return named == {mult}"),
    ("scale words may name several scales", "return named == {mult} and", "return mult in named and"),
    ('thousands marks not read', '            if prev not in DIGITS and prev not in ".," and nxt not in DIGITS:\n                out.add(10**3)\n            i = s.find(m, i + 1)\n    cw =', '            i = s.find(m, i + 1)\n    cw ='),
    # conversion and rounding
    ("magnitude keeps the sign", 'if fs["sign"] == "magnitude":\n            v = abs(v)', 'if fs["sign"] == "magnitude":\n            v = v'),
    ("finance-cost rule ignored", 'elif fs["sign"] == "finance_cost":', "elif False:"),
    ("always rounded down", 'q = _ceil_div(num, den) if rounding == "up" else num // den', "q = num // den"),
    ("rounded toward zero", 'q = _ceil_div(num, den) if rounding == "up" else num // den', "q = (abs(num) // den) * (1 if num >= 0 else -1)"),
    ("decimals ignored", "num, den = v * 10**decimals, d * step", "num, den = v, d * step"),
    ("JSON floats parsed", "out = json.loads(s, parse_float=str)", "out = json.loads(s)"),
    ("12.450 read as a number", 'if dot and "," not in s and len(frac) == 3', 'if False and dot and "," not in s and len(frac) == 3'),
    ("page not cut", "        text = text[:PAGE_CHARS]\n", ""),

    ("note references read as decimal commas", "for ch in _drop_note_refs(str(page or \"\").lower()) + \" \":", "for ch in str(page or \"\").lower() + \" \":"),
    ("1.234,567 not decimal comma", 'if "." in r and r.index(".") < r.rindex(","):\n                return True', 'if False:\n                return True'),
    ("1.234.567 not decimal comma", 'if len(parts) >= 3 and all(len(x) == 3', 'if False and len(parts) >= 3 and all(len(x) == 3'),
    ("stored figure cap off", 'if abs(stored) > MAX_FIGURE:\n            return {"kind": "NO_READING", "reason": "N2_FORMAT"}', 'if False:\n            return {"kind": "NO_READING", "reason": "N2_FORMAT"}'),
    ("yes accepts anything", 'return str(v).strip().lower() in ("yes", "true", "1")', 'return str(v).strip().lower() not in ("no", "")'),
    ("markers not removed", 'text = text.replace(PAGE_BEGIN, " ").replace(PAGE_END, " ").replace("=====", " ")', "text = text"),
    # leader result checks and agreement
    ("leader figure off the step", ' or v % int(fs["step"]) != 0:', ":"),
    ("leader figure keys not checked", "if not isinstance(figs, dict) or sorted(figs.keys()) != sorted(keys):", "if not isinstance(figs, dict):"),
    ("leader negative magnitude", 'if fs["sign"] == "magnitude" and v < 0:\n            raise', "if False:\n            raise"),
    ("unknown reason accepted", 'if r.get("reason") not in NO_READING_REASONS:', "if False:"),
    ("leader error accepted", "if not isinstance(leader_result, gl.vm.Return):\n                return False", "if not isinstance(leader_result, gl.vm.Return):\n                return True"),
    ("figures not compared", 'return a["figures"] == b["figures"]', "return True"),
    ("get_reading hides an official reading", '"has_official": p["official"] is not None', '"has_official": False'),
    ('get_reading hides the clock', '"clock": int(self.clocks[report_id]),\n               "final_clock"', '"clock": 0,\n               "final_clock"'),
    ("reason not compared", 'return a.get("reason", "") == b.get("reason", "")', "return True"),
    ("kind not compared", 'if a["kind"] != b["kind"]:\n        return False', 'if False:\n        return False'),
    # third review and finality
    ("'(in thousands)' not a heading", ' or (prev_word == ["in"] and not of_noun) or', ' or'),
    ("'Thousands' alone not a heading", ' or after_currency or plural_alone:', ' or after_currency:'),
    ('TEUR not a heading', '            if tok in ("t" + low, "k" + low):\n                out.add(10**3)\n            if tok in ("m" + low, "mio"):\n                out.add(10**6)\n            after_currency', '            after_currency'),
    ('TEUR not a copied scale', '            if tok in ("t" + low, "k" + low):\n                out.add(10**3)\n            if tok in ("m" + low, "mio", "mln"):', '            if tok in ("m" + low, "mio", "mln"):'),
    ("'m EUR' and 'k€' not a heading", '                        if (after_currency or before_currency) and not area_or_class:', '                        if after_currency and not area_or_class:'),
    ('a scaled copy ignores loose scales', ' and _loose_scales(lines, code) <= {mult}', ''),
    ('a scale word anywhere near nothing counts', '        if any(t in cw for t in _name_words(s[:a]).split()[-3:] + _name_words(s[b:]).split()[:3]):', '        if True:'),
    ('a change after the amount read', ' and not _change_after(line[b + j + len(value_n):]):', ':'),
    ('EPS labels take the heading scale', '    if any(x in lw for x in PER_SHARE_ABBR) or "/share" in label_n or "/unit" in label_n:\n        return True', '    if "/share" in label_n or "/unit" in label_n:\n        return True'),
    ('non-breaking hyphen not a minus', '"\\u2010", "\\u2011", ', ''),
    ('an unreadable mark before the value ignored', '    if k > 0 and not line[k - 1].isalnum() and line[k - 1] not in BEFORE_OK:\n        return True', '    if False:\n        return True'),
    ('currency cells hide an empty cell', '    toks = [t for t in s.replace(":", " ").split() if t not in _currency_words(code) and t not in SYMBOLS]', '    toks = s.replace(":", " ").split()'),
    ('an ellipsis is not an empty cell', '"\\u2026", "...", "..", ', ''),
    ('a lone star is not an empty cell', '"..", "*", ".", "|*", "|."', '"..", ".", "|."'),
    ('a footnote star on the label refuses', '                    btw = btw[1:] if btw.startswith("*") else btw', '                    pass'),
    ("next period's end on the page ignored", '    for t in later:\n        ls, ld = _date_forms(t)', '    for t in ():\n        ls, ld = _date_forms(t)'),
    ('a date earlier on the line ignored', ' and not _date_before(line, i):', ':'),
    ('an offset after UTC accepted', '                if r[:1] in ("+", "-") and r[1:2].isdigit():\n                    ok = False', '                if False:\n                    ok = False'),
    ('prior words inside other words', '    if not _has_word(line[:i], PRIOR_WORDS)', '    if not any(w in line[:i] for w in PRIOR_WORDS)'),
    ('abbreviated months not read', 'for m in (MONTHS[last.month - 1], MONTH_ABBR[last.month - 1])', 'for m in (MONTHS[last.month - 1],)'),
    ('ambiguous numeric dates read', '        if dd > 12:  # day first', '        if True:  # day first'),
    ('the scale read at the first copy of the digits', '    k = line.find(v) if at is None else at', '    k = line.find(v)'),
    ('LTM word after the value counts', 'any(_phrase_on_page(line[:at], w) for w in LTM_WORDS)', 'any(_phrase_on_page(line, w) for w in LTM_WORDS)'),
    ('superscripts kept on the page', '    for c in SUPERSCRIPTS:\n        s = s.replace(c, " ")\n', ''),
    ('superscripts kept in the copy', '        value = "".join(c for c in str(f.get("value")) if c not in SUPERSCRIPTS)', '        value = f.get("value")'),
    ('duplicate page URLs accepted', '        if len(set(u.lower() for u in urls)) != len(urls):', '        if False:'),
    ('no confirm_read posted', '            gl.get_contract_at(gl.message.contract_address).emit(on="finalized").confirm_read(report_id, n, _official_hash(p["official"]))', '            pass'),
    ('confirm_read posted on acceptance', 'gl.get_contract_at(gl.message.contract_address).emit(on="finalized").confirm_read(', 'gl.get_contract_at(gl.message.contract_address).emit(on="accepted").confirm_read('),
    ('no confirm_clock posted', '            gl.get_contract_at(gl.message.contract_address).emit(on="finalized").confirm_clock(report_id, now)', '            pass'),
    ('confirm_clock posted when no window closes', '        if any(old < _closes(spec, n) <= now and', '        if any(old <= now and'),
    ('anyone confirms', '        if gl.message.sender_address != gl.message.contract_address:\n            raise', '        if False:\n            raise'),
    ('confirm_read ignores the hash', '        ok = p["official"] is not None and _official_hash(p["official"]) == reading_hash', '        ok = p["official"] is not None'),
    ('finalized clock runs back', '        if clock > int(self.final_clocks.get(report_id) or 0):', '        if True:'),
    ('READ finalized without its mark', '(st == "READ" and p.get("finalized") is True)', '(st == "READ")'),
    ('MISSING finalized before its close is finalized', '(st == "MISSING" and out["final_clock"] >= _closes(spec, n))', '(st == "MISSING")'),
    # fourth review
    ('a change word straight after the amount ignored', '    if change_word(k) >= 0:\n        return True\n    # a bracket', '    if False:\n        return True\n    # a bracket'),
    ('after a comma any change word is a level', '        e = change_word(j)\n        if e < 0:\n            return False', '        e = change_word(j)\n        if True:\n            return False'),
    ('a bracket after the amount not skipped', '    if k < len(toks) and toks[k] == "(":\n        while k', '    if False:\n        while k'),
    ("'or 9% higher' not a change", '    if k < len(toks) and toks[k] == "or":\n        # \'or 9% higher\'', "    if False:\n        # 'or 9% higher'"),
    ('mln and crore after the value ignored', '            if nxt in OWN_SCALE_WORDS:\n                found.add(OWN_SCALE_WORDS[nxt])', '            pass'),
    ("copied 'mln' names no scale", '            if tok in ("m" + low, "mio", "mln"):', '            if tok in ("m" + low, "mio"):'),
    ("copied 'bln' names no scale", '            if tok in ("bln", "mrd"):\n                out.add(10**9)', '            if False:\n                out.add(10**9)'),
    ('pence and cents not refused', '    if _subunit(str(scale_text or "")) or _subunit(line) or any(_subunit(x) for x in _rows_above(lines, line)):\n        return False', '    if False:\n        return False'),
    ("'(p)' not pence", '    if "\\u00a2" in text or "(p)" in _norm(text):', '    if "\\u00a2" in text:'),
    ("'in thousands of ports' a heading", ' or (prev_word == ["in"] and not of_noun) or', ' or prev_word == ["in"] or'),
    ("'thousands of Canadian dollars' prose", 'not any(w in _currency_words(code) + MONEY_NOUNS for w in nxt_words[1:4])', 'nxt_words[1] not in _currency_words(code)'),
    ('a trailing minus ignored', '    if after == "-" and not value_n.endswith("-"):\n        return False', '    if False:\n        return False'),
    ('any month word is a date', '            if any(x.isdigit() or x[:-2].isdigit() and x[-2:] in ("st", "nd", "rd", "th") for x in near):', '            if True:'),
    ('a later end anywhere refuses', '        if any(_period_line(line) and (_printed(line, ls, ls)', '        if any((_printed(line, ls, ls)'),
    ('remark posts no confirm_read', '            me.emit(on="finalized").confirm_read(report_id, n, _official_hash(p["official"]))\n            return {"ok": True, "report_id": report_id, "period": n, "posted": "confirm_read"}', '            return {"ok": True, "report_id": report_id, "period": n, "posted": "confirm_read"}'),
    ('remark posts no confirm_clock', '            me.emit(on="finalized").confirm_clock(report_id, clock)\n            return', '            return'),
    ('remark posts again when marked', '            if p.get("finalized") is True:\n                return', '            if False:\n                return'),
    ('remark on a period with no final answer', '        if clock >= _closes(spec, n):\n            if int(self.final_clocks', '        if True:\n            if int(self.final_clocks'),
    ("leading digit or group ignored", 'if before and (before.isalnum() or before in ".,\'"):', "if False:"),
    # fifth review
    ("'9 per cent' not a percentage", '        if toks[k + 1] == "per" and toks[k + 2:k + 3] == ["cent"]:\n            return 3', '        if False:\n            return 3'),
    ('the cent sign not cents', '    if "\\u00a2" in text or "(p)" in _norm(text):', '    if "(p)" in _norm(text):'),
    ('pence in the column heads ignored', ' or any(_subunit(x) for x in _rows_above(lines, line)):\n        return False  # pence', ':\n        return False  # pence'),
    ("'per cent' read as cents", ' and not (t in ("cent", "cents") and k > 0 and toks[k - 1] == "per")', ''),
    ("'months to' not a period line", '"months to", ', ''),
    ("'x 1,000' not a heading", '        if j >= 0 and toks[j] in ("x", "in"):\n            out.add(mult)', '        if False:\n            out.add(mult)'),
    ("a bare 'EUR 1,000' names a heading", '        if j >= 0 and toks[j] in ("x", "in"):', '        if True:'),
    ("'000 omitted' not a heading", '    if "000 omitted" in s or "000s omitted" in s:\n        out.add(10**3)', '    if False:\n        out.add(10**3)'),
    ("'T€' not a heading", '            if tok == "t" and s[j:j + 1] in syms and not attached:\n                out.add(10**3)', '            if False:\n                out.add(10**3)'),
    ("'EUR (m)' and '£'m' not a heading", '            after_currency = after_currency or any(before.endswith(x + " (") or before.endswith(x + "(") or before.endswith(x + "\'") for x in syms + [low])', '            pass'),
    ("prose 'a million' counts as a scale", ' or prev in PROSE_BEFORE:', ':'),
    ("prose 'thousands of ports' counts as a scale", '            if toks[k + 1:k + 2] == ["of"] and not any(w in _currency_words(code) + MONEY_NOUNS for w in toks[k + 2:k + 5]):\n                continue', '            if False:\n                continue'),
    ('a copied heading form names no scale', '    named = _scale_mentions(st, code) | _heading_scales(st, code)', '    named = _scale_mentions(st, code)'),
    ('trillions after the value ignored', '                   "trillion": 10**12, "trillions": 10**12, "tn": 10**12, "trn": 10**12,', '                  '),
    ("'greater than' not a comparative", '"short", "greater", "larger",', '"short", "larger",'),
    ("a level 'up from' refused", "            return False  # 'up from USD 14.9 million'", "            pass  # 'up from USD 14.9 million'"),
    ("a level 'up 9%' refused", "        return False  # 'up 9%', 'an increase of 9%'", "        pass  # 'up 9%', 'an increase of 9%'"),
    ("'year-over-year increase' not a change", '        while j < len(toks) and toks[j] in MODIFIERS:\n            j += 1', '        pass'),
    ("'up on the prior year at' read as a level", ' and toks[j] not in ("at", "to", ","):', ':'),
    # sixth review
    ("'as per' makes a total per share", '    return any(w == "per" and any(x in PER_WHAT for x in lw[k + 1:k + 6]) for k, w in enumerate(lw))', '    return "per" in lw'),
    ('a per-share copy with its own scale word read', '        return mult == 1 and not own and st', '        return mult == 1 and st'),
    ("'£ 000' not a heading", ' + ((sym + " 000",) if sym else ()):', ':'),
    ('first word of a line never scanned', '            if (prev != "" and prev[-1] in DIGITS) or t in SINGLE_SCALES', '            if prev[-1:] in DIGITS or t in SINGLE_SCALES'),
    ("'mil' read as millions", '"mil": 0,', '"mil": 10**6,'),
    ("'Tsd.' not a heading word", '("thousands", "thousand", "k", "tsd", "tausend", "milliers")', '("thousands", "thousand", "k")'),
    ("'year ending' outlook refuses the page", '    return _has_word(line, ("ended", "months to",', '    return _has_word(line, ("ended", "ending", "months to",'),
    ("'in 1,000 stores' a heading", "            continue  # 'in 1,000 stores'", "            pass  # 'in 1,000 stores'"),
    ("a year after 'on' read as an amount", ' and not _is_pct(toks, j) and not _is_year(toks[j]):', ' and not _is_pct(toks, j):'),
    ("'zlotys' not a money noun", '"shekels", "zlotys", ', '"shekels", '),
    # seventh review (v8)
    ("two words only after 'per'", 'any(x in PER_WHAT for x in lw[k + 1:k + 6])', 'any(x in PER_WHAT for x in lw[k + 1:k + 3])'),
    ("four words only after 'per'", 'any(x in PER_WHAT for x in lw[k + 1:k + 6])', 'any(x in PER_WHAT for x in lw[k + 1:k + 5])'),
    ("'depositary' not a share word", '            "depositary", "depository", "stock")', '            "stock")'),
    ("'security' not a share word", '"stapled", "security", "securities",', '"stapled",'),
    ("'GDR' not a share word", '"gdr", "gdrs",', ''),
    ('a spaced dash not a comma', 'raw = rest[:stop].lower().replace(" - ", " , ")', 'raw = rest[:stop].lower()'),
    ('a decimal point splits a percentage', 'or ch == "%" or keep(i, ch) else', 'or ch == "%" else'),
    ("'in EUR 1,000, unless' is prose", 'if j == k - 1 and after and', 'if after and'),
    ("'in 1,000 US dollars' is prose", 'not in cw + MONEY_NOUNS:\n            continue', 'not in cw:\n            continue'),
    ('a per-share symbol may touch a letter', '(b == len(text_n) or not text_n[b].isalpha()) \\', '(True) \\'),
    ('bare: a letter before the phrase', '(a == 0 or not text_n[a - 1].isalnum() or not phrase_n[0].isalnum()) and (b == len(text_n) or not text_n[b].isalpha())', 'True and (b == len(text_n) or not text_n[b].isalpha())'),
    ('bare: a digit after the phrase', '                and (b == len(text_n) or not text_n[b].isalnum() or not phrase_n[-1].isalnum()) \\', '                and True \\'),
    ('bare: an empty copy', 'i = text_n.find(phrase_n) if phrase_n != "" else -1', 'i = text_n.find(phrase_n)'),
    ("per share '(in EUR)' refused", '        if st.startswith("in "):\n            st = st[3:].strip("()[] ")', '        if False:\n            st = st[3:].strip("()[] ")'),
    ("'per m2' names millions", '            area_or_class = prev_word in (["per"], ["sq"], ["square"], ["cubic"], ["class"], ["series"], ["tranche"])', '            area_or_class = False'),
    ("'per sq m' names millions", '(["per"], ["sq"], ["square"], ["cubic"], ["class"], ["series"], ["tranche"])', '(["per"], ["square"], ["cubic"], ["class"], ["series"], ["tranche"])'),
    ("'mil' in a heading ignored", '            if t == "mil":\n                out.add(0)', '            if False:\n                out.add(0)'),
    # v9: per share declared in the spec
    ('per_share not a figure field', 'FIGURE_KEYS = ("key", "label_hint", "labels", "ltm", "decimals", "step", "rounding", "sign", "per_share")', 'FIGURE_KEYS = ("key", "label_hint", "labels", "ltm", "decimals", "step", "rounding", "sign")'),
    ('per_share defaults to the wording', 'per_share = f.get("per_share")\n', 'per_share = f.get("per_share", looks)\n'),
    ('a per-share label may be declared a total', '    if looks and not per_share:\n', '    if False:\n'),
    ('per_share need not be a bool', '    if not isinstance(per_share, bool):\n        return f"figure {key}: per_share must be true (an amount per share or unit) or false (a total); it has no default", None', '    if False:\n        return f"figure {key}: per_share must be true (an amount per share or unit) or false (a total); it has no default", None'),
    ('the label hint not checked for per share', 'for lab in clean + [_norm_label(hint)])', 'for lab in clean)'),
    ('the copied label decides per share', 'fs["per_share"] is True', '_per_share_label(label_n)'),
    ('a scale before a per-share value allowed', '        if _heading_scales(before, code) or any(_scale_mentions(w, code) for w in words if w not in SINGLE_SCALES):\n            return False', '        if False:\n            return False'),
    ('scale words before a per-share value ignored', ' or any(_scale_mentions(w, code) for w in words if w not in SINGLE_SCALES):', ':'),
    ('share-class letters before a per-share value count', 'for w in words if w not in SINGLE_SCALES)', 'for w in words)'),
    ("'Class M EUR' names millions", '(["per"], ["sq"], ["square"], ["cubic"], ["class"], ["series"], ["tranche"])', '(["per"], ["sq"], ["square"], ["cubic"])'),
    ("the reading's units omit per_share", ',\n                                                   "per_share": f.get("per_share") is True}', '}'),
    ("'fils' not a sub-unit", '"cps", "fils", ', '"cps", '),
    ("'cps' not a sub-unit", '"eurocents", "cps",', '"eurocents",'),
    ("'kopecks' not a sub-unit", '"kopeck", "kopecks",', '"kopeck",'),
    ("'paise' not a sub-unit", '"paise", ', ''),
    # v10: the eighth and ninth reviews
    ("currency prefix kept", "if tok != low and tok.startswith(low):", "if False:"),
    ('per_share true without the wording', '    if per_share and not looks:\n', '    if False:\n'),
    ('a glued code scale after the value ignored', '        if nxt != low and nxt.startswith(low):\n            nxt = nxt[len(low):]', '        if False:\n            nxt = nxt[len(low):]'),
    ('the whole line before a per-share value checked', '        if label_n and before.rfind(label_n) >= 0:\n', '        if False:\n'),
    ('a code with a scale suffix is a per-share currency', '        cur = {code.lower()} |', '        cur = set(_currency_words(code)) |'),
    ("'US$' not a per-share currency", '        cur |= {"us$"} if code == "USD" else set()', '        pass'),
    ('bare: a letter before a symbol', '                and (a == 0 or not text_n[a - 1].isalpha()):', '                and True:'),
    ('a qualifier before a spaced dash starts a phrase', "        return not _qualifier_before(lead[:-1])  # a spaced dash: '- Revenue', 'Q3 - Revenue'; not 'Non-GAAP - EBITDA'", "        return True  # a spaced dash: '- Revenue', 'Q3 - Revenue'; not 'Non-GAAP - EBITDA'"),
    ('a list number in the middle of a line', '(len(lead) == len(word) or lead[:-len(word)].rstrip()[-1:] == "|")', 'True'),
    ('two letters are a list letter', '(len(word) == 2 and word[0].isalpha())', '(len(word) <= 3 and word[0].isalpha())'),
    ("'1.' not a list number", 'number = word[:-1].isdigit() or', 'number = False or'),
    ('roman numerals not list numbers', '(word[:-1] != "" and all(c in "ivx" for c in word[:-1]))', 'False'),
    ("'adj' not a qualifier", '("adjusted", "adj", ', '("adjusted", '),
    ('qualifiers match inside words', 'return any(words.endswith(" " + q) for q in QUALIFIERS)', 'return any(words.endswith(q) for q in QUALIFIERS)'),
    ("'NAVPS' not per share", 'PER_SHARE_ABBR = ("eps", "dps", "navps", ', 'PER_SHARE_ABBR = ("eps", "dps", '),
    ("'per common stock' not per share", '"depository", "stock")', '"depository")'),
    ("'(-)' with spaces not an empty cell", ' or "".join(s.split()).endswith("(-)"):', ':'),
    ("'for the year' does not link", '"period", "year", "full", "half",', '"period",'),
    ('the currency sign with a scale refused', '    if uniq and raw.strip().startswith(uniq) and raw.strip()[len(uniq):].strip(" \'\\u2019").lower() in SIGN_SCALES:', '    if False:'),
    ("a glued footnote mark on the figure's line ignored", '        if _marked(line, marks):\n', '        if False:\n'),
    ('marks: a mark after a space counts', 'if mark == "" or before == "" or before[-1].isspace():', 'if mark == "" or before == "":'),
    ('marks: <sub> not read', 'if tag not in ("sup", "sub")', 'if tag not in ("sup",)'),
    ('marks: inline tags leave a space', 'out.append("" if name in INLINE_TAGS else " ")', 'out.append(" ")'),
    ('marks: entities kept', '    return "".join(out).replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")', '    return "".join(out)'),
    ('marks: a piece inside a tag', '        s = " " + s[k + 1:]  # the piece starts inside a tag', '        pass'),
    ('marks: no cap', '    while len(out) < MAX_MARKS:', '    while True:'),
    ('the HTML render not read', '        marks = _glued_marks(gl.nondet.web.render(url, mode="html", wait_after_loaded=RENDER_WAIT))', '        marks = set()'),
    ('a comma starts a phrase', 'LIST_MARKS = "|:;', 'LIST_MARKS = ",|:;'),
    ('pence one row up only', 'def _rows_above(lines: list, line: str, n: int = 3)', 'def _rows_above(lines: list, line: str, n: int = 1)'),
    ("the official reading keeps period 0's URL", '"url": _page_url(spec, n), "attempt"', '"url": _page_url(spec, 0), "attempt"'),
]

EARNOUT = [
    ("nothing-below-floor rule off", "if value <= floor:\n        return 0", "if False:\n        return 0"),
    ("all-above-target rule off", "if value >= target:\n        return amount", "if False:\n        return amount"),
    ("share rounded up", "return amount * (value - floor) // (target - floor)", "return -(-amount * (value - floor) // (target - floor))"),
    ("missing ignores the pinned share", 's = deal["amount"] * deal["missing_seller_bp"] // BP', "s = 0"),
    ("missing share rounded up", 's = deal["amount"] * deal["missing_seller_bp"] // BP', 's = -(-deal["amount"] * deal["missing_seller_bp"] // BP)'),
    ("missing share above 100%", "not 0 <= missing_bp <= BP:", "not 0 <= missing_bp:"),
    ("missing share may be text", 'if isinstance(missing_bp, bool) or not isinstance(missing_bp, int) or', "if"),
    ("reader digest not checked at settle", 'if reading.get("digest") != deal["digest"] or reading.get("period") != deal["period"]:\n        raise', "if False:\n        raise"),
    ("reader period not checked at create", 'if reading.get("digest") != digest or reading.get("period") != period:\n        return', "if False:\n        return"),
    ("pinned after the period ended", 'if reading.get("status") != "NOT_DUE" or now >= end:', 'if reading.get("status") not in ("NOT_DUE", "WAITING"):'),
    ("own time not checked", 'if reading.get("status") != "NOT_DUE" or now >= end:', 'if reading.get("status") != "NOT_DUE":'),
    ("existing reading ignored", 'if reading.get("has_official") is not False:', "if False:"),
    ("reader clock ignored", "if isinstance(clock, bool) or not isinstance(clock, int) or clock >= end:", "if False:"),
    ("period end missing accepted", 'if isinstance(end, bool) or not isinstance(end, int):\n        return "the reader gave no period end"', 'if end is None:\n        end = 2**62'),
    ("pinned digest not checked", 'if not isinstance(digest, str) or digest != report.get("digest"):', "if not isinstance(digest, str):"),
    ("figure not checked", "if figure not in figs:", "if False:"),
    ("period upper bound not checked", 'not 0 <= period < len(report["spec"]["period_ends"])', "not 0 <= period"),
    ("target may equal floor", "if target <= floor:", "if target < floor:"),
    ("leading zeros allowed", '(len(body) > 1 and body[0] == "0")', "False"),
    ("seller may be buyer", "if seller_hex.lower() == buyer.lower():", "if False:"),
    ("zero escrow accepted", "if value <= 0:\n            return self._refuse", "if value < 0:\n            return self._refuse"),
    ("refused value kept", "        self._credit(gl.message.sender_address.as_hex, value)\n        return {\"ok\": False", "        return {\"ok\": False"),
    ("withdraw above the credit", "if not 0 < amount <= have:", "if not 0 < amount:"),
    ("not-final status settles", 'if st != "READ":\n        if st == "CLOSING":', 'if st not in ("READ", "OPEN"):\n        if st == "CLOSING":'),
    ('settle ignores the finalized mark', '    if st in ("READ", "MISSING") and reading.get("finalized") is not True:', '    if False:'),
    ("terms digest leaves out the seller", 'body = {"buyer": buyer.lower(), "seller": seller.lower(), **terms}', 'body = {"buyer": buyer.lower(), **terms}'),
    ("anyone accepts", 'if gl.message.sender_address.as_hex.lower() != d.seller.lower():\n            raise gl.vm.UserError("only the seller can accept")', 'if False:\n            raise gl.vm.UserError("only the seller can accept")'),
    ("accept without the digest", 'if not isinstance(terms_digest, str) or terms_digest != d.terms_digest:', "if False:"),
    ("accept twice", 'if d.state != "OFFERED":\n            raise gl.vm.UserError("the deal is " + d.state + ", not OFFERED")', 'if False:\n            raise gl.vm.UserError("the deal is " + d.state + ", not OFFERED")'),
    ("accept after the end", '        p = _before_end_problem(reading, now)\n        if p:\n            raise gl.vm.UserError(p + ": too late to accept")', "        pass"),
    ("anyone cancels", 'if gl.message.sender_address.as_hex.lower() != d.buyer.lower():\n            raise gl.vm.UserError("only the buyer can cancel")', 'if False:\n            raise gl.vm.UserError("only the buyer can cancel")'),
    ("accepted deal cancelled", 'if d.state != "OFFERED":\n            raise gl.vm.UserError("the deal is " + d.state + ": only', 'if d.state == "SETTLED":\n            raise gl.vm.UserError("the deal is " + d.state + ": only'),
    ("cancel keeps the money locked", '        self.locked = u256(int(self.locked) - deal["amount"])\n        self._credit(d.buyer, deal["amount"])\n        d.state = "CANCELLED"', '        d.state = "CANCELLED"'),
    ("offer expires early", 'if now < deal["period_end_ts"]:\n                raise', 'if False:\n                raise'),
    ("expired offer pays the seller", '            self._credit(d.buyer, deal["amount"])\n            d.state = "EXPIRED"', '            self._credit(d.seller, deal["amount"])\n            d.state = "EXPIRED"'),
    ("settled deal pays again", 'if d.state in ("SETTLED", "CANCELLED", "EXPIRED"):', 'if d.state in ("CANCELLED", "EXPIRED"):'),
    ('settle reads the reading as of a fixed time', '        reading = gl.get_contract_at(self.reader).view().get_reading(deal["report_id"], deal["period"], now)', '        reading = gl.get_contract_at(self.reader).view().get_reading(deal["report_id"], deal["period"], 2**40)'),
]

# Equivalent mutants, not counted: each removes a check that a later check
# now makes redundant, so no input can tell the mutant from the contract.
#   superscript footnote marks kept: _norm drops them for every line first;
#   totals read in whole units: the last check (named == {mult}) can never hold
#     for units, since no scale word names 1; the explicit rule documents it;
#   sign before the value ignored: _sign_across_currency refuses any mark before
#     the digits that is not a separator, '(' and '-' included;
#   'mill.' after the value ignored: 'mill' is also in SCALE_WORDS, which
#     _own_scale reads first;
#   ', a 9% increase' a change: a percentage is never a modifier or a change
#     word, so change_word() returns -1 and the same 'level' answer follows;
#   'M€' not a heading (redundant, not strictly equivalent): the 'm €' rule
#     (before_currency) also reads it; the two differ only right after per, sq,
#     square, cubic, class, series or tranche ('Class M€'), where the M€ rule
#     still names millions and so can only refuse a scaled copy.
EQUIVALENT_READER = [
    ('totals read in whole units', '    if mult == 1:\n        return False  # totals', '    if False:\n        return False  # totals'),
    ("superscript footnote marks kept", "        for c in SUPERSCRIPTS:\n            line = line.replace(c, \" \")", "        pass"),
    ("sign before the value ignored", 'if before in ("(", "-") and not value_n.startswith(("(", "-")):', "if False:"),
    ("'M€' not a heading", '            if tok == "m" and s[j:j + 1] in syms and not attached:\n                out.add(10**6)', '            if False:\n                out.add(10**6)'),
    ("'mill.' after the value ignored", '"mill": 10**6, "mil": 0, ', '"mil": 0, '),
    ("', a 9% increase' a change", '        if j < len(toks) and _is_pct(toks, j):\n            return False', '        if False:\n            return False'),
]

TARGETS = {
    "reader": ("contracts/report_reader.py", "RR_CONTRACT", READER, ["tests/direct/test_report_reader.py", "tests/direct/test_report_reader_review.py", "tests/direct/test_report_reader_review2.py",
                                                                  "tests/direct/test_report_reader_review3.py", "tests/direct/test_report_reader_review4.py", "tests/direct/test_report_reader_review5.py", "tests/direct/test_report_reader_review6.py", "tests/direct/test_report_reader_review7.py", "tests/direct/test_report_reader_review8.py", "tests/direct/test_report_reader_review9.py",
                                                                  "tests/direct/test_report_reader_finality.py"]),
    "earnout": ("examples/consumer/earn_out_example.py", "EO_CONTRACT", EARNOUT, ["tests/direct/test_earn_out.py", "tests/direct/test_earn_out_review3.py"]),
}


def run(name: str) -> tuple:
    rel, var, mutants, tests = TARGETS[name]
    src = (ROOT / rel).read_text()
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    tmp = Path(tempfile.mkdtemp(prefix=f"{name}-mutants-"))
    caught = 0
    for i, (label, old, new) in enumerate(mutants, 1):
        n = src.count(old)
        if n != 1:
            print(f"SETUP ERROR  {name} {label}: pattern found {n} times")
            sys.exit(2)
        path = tmp / f"mutant_{i:02d}.py"
        path.write_text(src.replace(old, new))
        r = subprocess.run([sys.executable, "-m", "pytest", *tests, "-q", "-x", "-p", "no:cacheprovider"],
                           cwd=ROOT, env={**env, var: str(path)}, capture_output=True, text=True)
        ok = r.returncode != 0
        caught += ok
        print(f"{'caught ' if ok else 'MISSED '} {name} {i:2d} {label}", flush=True)
    return caught, len(mutants)


def main() -> int:
    names = sys.argv[1:] or list(TARGETS)
    total = got = 0
    for nm in names:
        c, n = run(nm)
        got, total = got + c, total + n
        print(f"{nm}: {c} of {n} mutants caught\n", flush=True)
    print(f"{got} of {total} mutants caught")
    return 0 if got == total else 1


if __name__ == "__main__":
    sys.exit(main())
