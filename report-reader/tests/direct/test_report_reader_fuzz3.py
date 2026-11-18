import json, random
from tests.direct.test_report_reader import env, mod, iso  # noqa
from tests.direct.test_report_reader_review import TAR, E0, live_spec, fig, ans, TARNWICK_RENDERED, T_FIGS, BASE_FIGS  # noqa

ALPH = list("abcdeEURmk$€£()-–—,.:;|%' \n\t0123456789¹²") + ["EUR", "million", "thousands", "Revenue", "note ", "2026-11-18 08:15", "UTC", "prior ", "LTM ", "(EUR)", "in ", "per share"]

def test_fuzz(env, mod):
    rnd = random.Random(7)
    p, spec = mod._spec_problem(json.dumps(live_spec()), E0 - 1800)
    bad = []
    for it in range(4000):
        page = TARNWICK_RENDERED
        # mutate the page
        for _ in range(rnd.randint(1, 8)):
            i = rnd.randrange(len(page))
            page = page[:i] + rnd.choice(ALPH) + page[i + rnd.randint(0, 3):]
        figs = {k: dict(v) for k, v in T_FIGS.items()}
        for k in figs:
            for fld in ("value", "scale", "scale_text", "line_label"):
                if rnd.random() < 0.3:
                    figs[k][fld] = rnd.choice([None, 0, 1.5, True, [], {}, "", rnd.choice(ALPH) * rnd.randint(1, 3), figs[k][fld] + rnd.choice(ALPH)])
        a = json.loads(ans(TAR, figs).strip("`").replace("json\n", ""))
        if rnd.random() < 0.2:
            a["period_end_on_page"] = rnd.choice([None, 5, "2026-11-18", "2026-11-18 08:15:00.000", "x" * 20])
        try:
            mod._decimal_comma_page(page)
            mod._interpret(spec, 0, a, mod._clean_page(page))
        except Exception as e:
            bad.append((repr(e), page[:80], a))
    print(len(bad), bad[:3])
    assert not bad
