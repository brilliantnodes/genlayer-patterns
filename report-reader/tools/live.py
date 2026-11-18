#!/usr/bin/env python3
"""Run ReportReader and EarnOutExample live, on GenLayer Studio or Testnet
Bradbury Phase 2, and record every transaction.

    python tools/live.py <tag> <E0_unix> [--net studio|bradbury] [--reader 0x..] [--consumer 0x..]

The pages must already be live at
  https://privatecredit.brilliantnodes.com/report-reader/<tag>/<slug>/q-<n>.html
(tools/make_pages.py <tag> <E0> <dir>, then copied into that site).

Timeline (lag 5 min, window 30 min; Tarnwick's period n ends at E0 + 15n min):
  before E0     deploy, register six reports, a read before the window
                (refused), two earn-outs and one refused earn-out
  E0 + 5        period 0 of all six read; a second read of Tarnwick 0
                (refused); an earn-out pinned too late (refused); earn-out 1
                settled
  E0 + 20       Tarnwick period 1 read: not published
  E0 + 35       Tarnwick period 2 read; a read of a closed one-period report
  E0 + 50       tick settles Tarnwick period 1 as MISSING; earn-out 2
                settled (buyer refunded); withdrawals; totals reconciled

Studio: three throwaway accounts funded from Studio's faucet. Bradbury: two
test wallets whose key files are in BRADBURY_KEY_DIR (never printed). Every
company and figure is fictional; only test GEN moves.
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
G = 10**18
SITE = os.environ.get("RR_SITE", "https://privatecredit.brilliantnodes.com")
LAG, WIN = 5, 30
args = sys.argv[1:]
TAG, E0 = args[0], int(args[1])


def opt(name, default=""):
    return args[args.index(name) + 1] if name in args else default


NET = opt("--net", "studio")
BB = NET == "bradbury"
REC_PATH = ROOT / "examples" / f"live-{NET}-{TAG}.json"
REC = {"net": NET, "tag": TAG, "e0": E0, "site": SITE, "contracts": {}, "accounts": {}, "reports": {}, "deals": {}, "steps": []}


def utc(ts=None):
    return datetime.fromtimestamp(ts if ts is not None else time.time(), timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def log(msg):
    print(f"{utc()} {msg}", flush=True)


def save():
    REC_PATH.write_text(json.dumps(REC, indent=1, default=str))


def until(ts):
    while time.time() < ts:
        time.sleep(min(5, max(0.5, ts - time.time())))


def url_t(slug):
    return f"{SITE}/report-reader/{TAG}/{slug}/q-{{n}}.html"


# ------------------------------------------------------------------ backends

if not BB:
    from genlayer_py import create_account, create_client
    from genlayer_py.chains import studionet
    from genlayer_py.types import TransactionStatus

    ACCTS = {}

    def make_accounts():
        for role in ("alice", "bob", "carol"):
            a = create_account()
            c = create_client(chain=studionet, account=a)
            c.provider.make_request(method="sim_fundAccount", params=[a.address, 100 * G])
            ACCTS[role] = (c, a)
            REC["accounts"][role] = a.address

    def _wait(c, tx):
        deadline, last = time.time() + 900, None
        while time.time() < deadline:
            try:
                return c.wait_for_transaction_receipt(transaction_hash=tx, status=TransactionStatus.ACCEPTED, interval=3000, retries=20)
            except Exception as e:  # Studio's gateway sometimes answers 502/520 for a few seconds
                last = e
                time.sleep(5)
        raise RuntimeError(f"no receipt for {tx}: {last}")

    def _result(r):
        cd = r.get("consensus_data") or {}
        lr = cd.get("leader_receipt")
        lr = lr[0] if isinstance(lr, list) and lr else lr
        lr = lr if isinstance(lr, dict) else {}
        res = lr.get("result") or {}
        payload = res.get("payload") if isinstance(res, dict) else None
        if isinstance(payload, dict) and "readable" in payload:
            try:
                payload = json.loads(payload["readable"])
            except Exception:
                payload = payload["readable"]
        votes = cd.get("votes") or {}
        return {"status": r.get("status_name"), "execution": lr.get("execution_result"), "result": payload, "votes": votes}

    def deploy(role, path, cargs):
        c, a = ACCTS[role]
        tx = c.deploy_contract(code=Path(path).read_text(), args=cargs)
        r = _wait(c, tx)
        return tx, r.get("to_address") or r.get("recipient") or (r.get("data") or {}).get("contract_address")

    def send(role, addr, fn, fargs, value=0):
        """One send only: a retry after the node got it would be a second transaction."""
        c, a = ACCTS[role]
        tx = c.write_contract(address=addr, function_name=fn, args=fargs, value=value)
        return tx, _result(_wait(c, tx))

    def view(addr, fn, fargs):
        c, a = ACCTS["carol"]
        return c.read_contract(address=addr, function_name=fn, args=fargs)

    def balance(addr):
        c, a = ACCTS["carol"]
        r = c.provider.make_request(method="eth_getBalance", params=[addr, "latest"])
        return int(r["result"], 16)
else:
    JS = ROOT / "tools" / "bradbury"
    KEY_DIR = os.environ.get("BRADBURY_KEY_DIR", "/home/claude/keys")
    KEYS = {"alice": f"{KEY_DIR}/bradbury_rr.key", "bob": f"{KEY_DIR}/bradbury_rr2.key", "carol": f"{KEY_DIR}/bradbury_rr.key"}
    NOTHING = ("UNDETERMINED", "LEADER_TIMEOUT", "VALIDATORS_TIMEOUT", "CANCELED")

    def _node(role, *a, timeout=1800):
        p = subprocess.run(["node", "gl.mjs", *a], cwd=JS, capture_output=True, text=True, timeout=timeout,
                           env={**os.environ, "BRADBURY_KEY_FILE": KEYS[role]})
        objs = [json.loads(x) for x in p.stdout.splitlines() if x.startswith("{")]
        return objs

    def make_accounts():
        from eth_account import Account
        for role in ("alice", "bob"):
            REC["accounts"][role] = Account.from_key(Path(KEYS[role]).read_text().strip()).address
        REC["accounts"]["carol"] = REC["accounts"]["alice"]

    def _tx(h):
        o = _node("alice", "tx", h, timeout=300)
        return (o[-1].get("raw") if o else None) or {}

    def _decided(raw):
        st = str(raw.get("statusName", ""))
        return st in NOTHING or (st in ("ACCEPTED", "FINALIZED") and raw.get("resultName") not in (None, "", "IDLE"))

    def _wait_h(h, final=False):
        for _ in range(240):
            raw = _tx(h)
            if (str(raw.get("statusName")) == "FINALIZED") if final else _decided(raw):
                return raw
            time.sleep(10)
        return _tx(h)

    def deploy(role, path, cargs):
        o = _node(role, "deploy", str(path), json.dumps(cargs))
        d = next((x for x in reversed(o) if "ok" in x), {})
        raw = d.get("raw") or {}
        addr = raw.get("recipient") or raw.get("toAddress") or (raw.get("txDataDecoded") or {}).get("contractAddress")
        return d.get("hash"), addr

    def send(role, addr, fn, fargs, value=0, payees=""):
        o = _node(role, "write", addr, fn, json.dumps(fargs), str(value), payees)
        sent = next((x["sent"] for x in o if "sent" in x), None)
        d = next((x for x in reversed(o) if "ok" in x), {})
        h = d.get("hash") or sent
        raw = d.get("raw") or {}
        if h and not _decided(raw):
            raw = _wait_h(h)
        if str(raw.get("statusName")) in ("LEADER_TIMEOUT", "VALIDATORS_TIMEOUT"):
            raw = _wait_h(h, final=True)
        st = str(raw.get("statusName", ""))
        return h, {"status": st if st in NOTHING else raw.get("resultName"), "execution": raw.get("txExecutionResultName"),
                   "created": raw.get("createdTimestamp"), "result": None}

    def view(addr, fn, fargs):
        for i in range(3):
            o = _node("alice", "read", addr, fn, json.dumps(fargs), timeout=300)
            d = o[-1] if o else {}
            if d.get("ok"):
                return d["result"]
            time.sleep(10)
        raise RuntimeError(f"read {fn} failed: {d}")

    def balance(addr):
        o = _node("alice", "balance", addr, timeout=120)
        return int(o[-1]["result"])


def step(case, role, addr, fn, fargs, value=0, expect=None, **kw):
    log(f"{case}: {fn}{tuple(fargs)} from {role}" + (f" value {value}" if value else ""))
    try:
        tx, r = send(role, addr, fn, fargs, value, **kw)
    except Exception as e:
        tx, r = None, {"status": "SEND_FAILED", "error": str(e)[:300]}
    entry = {"case": case, "at": utc(), "from": REC["accounts"][role], "fn": fn, "args": fargs, "value": str(value), "tx": tx, **{k: v for k, v in r.items() if k != "votes"}}
    if r.get("votes"):
        entry["votes"] = r["votes"]
    if expect is not None:
        entry["expect"] = expect
    REC["steps"].append(entry)
    save()
    log(f"  -> {r.get('status')} / {r.get('execution')} / {json.dumps(r.get('result'), default=str)[:300]}")
    return tx, r


def reports():
    t = lambda m: datetime.fromtimestamp(E0 + m * 60, timezone.utc).strftime("%Y-%m-%d %H:%M")
    base_figs = [
        {"key": "revenue", "label_hint": "Revenue for the quarter", "labels": ["Revenue"], "ltm": False, "decimals": 0, "step": 1000, "rounding": "down", "sign": "as_printed"},
        {"key": "ltm_ebitda", "label_hint": "EBITDA for the last twelve months", "labels": ["EBITDA (last twelve months)", "LTM EBITDA"], "ltm": True, "decimals": 0, "step": 1000, "rounding": "down", "sign": "as_printed"},
        {"key": "net_finance_costs", "label_hint": "Net finance costs (net interest expense)", "labels": ["Net finance costs"], "ltm": False, "decimals": 0, "step": 1000, "rounding": "up", "sign": "finance_cost"},
        {"key": "total_debt", "label_hint": "Total borrowings", "labels": ["Total borrowings"], "ltm": False, "decimals": 0, "step": 1000, "rounding": "up", "sign": "magnitude"},
    ]
    out = {"tarnwick": {"issuer_name": "Tarnwick Harbour Holdings plc", "url_template": url_t("tarnwick"), "currency": "EUR",
                        "period_ends": [t(0), t(15), t(30)], "publish_lag_minutes": LAG, "read_window_minutes": WIN, "figures": base_figs}}
    for slug in ("ostravelle-draft", "ostravelle-adjusted", "ostravelle-comma", "ostravelle-injection", "ostravelle-old"):
        out[slug] = {"issuer_name": "Ostravelle Fibre SA", "url_template": url_t(slug), "currency": "EUR", "period_ends": [t(0)],
                     "publish_lag_minutes": LAG, "read_window_minutes": WIN, "figures": base_figs}
    return out


def main():
    make_accounts()
    save()
    reader = opt("--reader")
    if not reader:
        path = ROOT / "contracts" / "report_reader.py" if not BB else ROOT.parent / "bradbury" / "build" / "report_reader.py"
        tx, reader = deploy("alice", path, [])
        REC["contracts"]["reader"] = {"address": reader, "deploy_tx": tx}
        log(f"reader deployed at {reader} ({tx})")
    else:
        REC["contracts"]["reader"] = {"address": reader}
    consumer = opt("--consumer")
    if not consumer:
        path = ROOT / "examples" / "consumer" / "earn_out_example.py" if not BB else ROOT.parent / "bradbury" / "build" / "earn_out_example.py"
        tx, consumer = deploy("alice", path, [reader])
        REC["contracts"]["consumer"] = {"address": consumer, "deploy_tx": tx}
        log(f"consumer deployed at {consumer} ({tx})")
    else:
        REC["contracts"]["consumer"] = {"address": consumer}
    save()

    ids = {}
    for slug, spec in reports().items():
        tx, r = step(f"register {slug}", "alice", reader, "register_report", [json.dumps(spec)])
        count = view(reader, "get_counts", [])["reports"]
        rid = str(count)
        rep = view(reader, "get_report", [rid])
        if rep["spec"]["url_template"] != spec["url_template"]:
            rows = view(reader, "get_reports", [1, 50])
            rid = next(x["id"] for x in rows if view(reader, "get_report", [x["id"]])["spec"]["url_template"] == spec["url_template"])
            rep = view(reader, "get_report", [rid])
        ids[slug] = rid
        REC["reports"][slug] = {"id": rid, "digest": rep["digest"], "register_tx": tx, "periods": rep["periods"]}
        save()
    A = ids["tarnwick"]
    dA = REC["reports"]["tarnwick"]["digest"]

    step("read before the window opens (refused)", "carol", reader, "read", [A, 0], expect="error: window opens at E0+5")
    bob = REC["accounts"]["bob"]
    v1, v2 = (10 * G, 5 * G) if not BB else (G // 10, G // 20)
    step("earn-out 1: revenue, floor 10,000,000, target 20,000,000", "alice", consumer, "create", [bob, A, dA, 0, "revenue", "10000000", "20000000"], value=v1)
    step("earn-out 2: LTM EBITDA of period 1", "alice", consumer, "create", [bob, A, dA, 1, "ltm_ebitda", "0", "5000000"], value=v2)
    step("earn-out refused: wrong digest (value credited back)", "alice", consumer, "create", [bob, A, "00" * 32, 0, "revenue", "1", "2"], value=v2 // 5)
    REC["deals"] = {"count_after_setup": view(consumer, "totals", [])}
    save()

    until(E0 + LAG * 60 + 20)
    step("Tarnwick period 0: table page", "carol", reader, "read", [A, 0], expect="READ")
    for slug, exp in (("ostravelle-draft", "NO_READING N3_NOT_FINAL"), ("ostravelle-adjusted", "NO_READING N2_LABEL"),
                      ("ostravelle-comma", "NO_READING N2_FORMAT"), ("ostravelle-injection", "READ with the table's figures"),
                      ("ostravelle-old", "NO_READING N1_WRONG_PAGE or N2_WRONG_PERIOD")):
        step(f"{slug} period 0", "carol", reader, "read", [ids[slug], 0], expect=exp)
    step("Tarnwick period 0 read again (refused: one official reading)", "carol", reader, "read", [A, 0], expect="error")
    step("earn-out pinned after the period ended (refused, value credited back)", "alice", consumer, "create", [bob, A, dA, 0, "revenue", "1", "2"], value=v2 // 5)
    step("settle earn-out 1", "carol", consumer, "settle", ["1"], expect="seller paid on the straight line")

    until(E0 + (15 + LAG) * 60 + 20)
    step("Tarnwick period 1: not yet published", "carol", reader, "read", [A, 1], expect="NOT_PUBLISHED")
    step("settle earn-out 2 too early (refused)", "carol", consumer, "settle", ["2"], expect="error: no final answer yet")

    until(E0 + (30 + LAG) * 60 + 20)
    step("Tarnwick period 2: highlights page in millions", "carol", reader, "read", [A, 2], expect="READ")
    step("ostravelle-draft read after its window closed", "carol", reader, "read", [ids["ostravelle-draft"], 0], expect="CLOSED, MISSING")

    until(E0 + (15 + LAG + WIN) * 60 + 20)
    step("tick Tarnwick: period 1 settles as MISSING", "carol", reader, "tick", [A], expect="missing [1]")
    step("settle earn-out 2 (report missing: buyer refunded)", "carol", consumer, "settle", ["2"], expect="buyer refunded")

    acc = REC["accounts"]
    for role in ("bob", "alice"):
        if BB:
            step(f"withdraw ({role})", role, consumer, "withdraw", [0], payees=acc[role])
        else:
            step(f"withdraw ({role})", role, consumer, "withdraw", [0])

    final = {"counts": view(reader, "get_counts", []), "readings": {}, "deals": {}, "totals": view(consumer, "totals", []),
             "consumer_balance": str(balance(consumer))}
    for slug, rid in ids.items():
        n = len(REC["reports"][slug]["periods"])
        for i in range(n):
            final["readings"][f"{slug}:{i}"] = view(reader, "get_reading", [rid, i, int(time.time())])
            final["readings"][f"{slug}:{i}"]["attempts_kept"] = view(reader, "get_attempts", [rid, i])["kept"]
    for did in ("1", "2"):
        final["deals"][did] = view(consumer, "get_deal", [did])
    final["claimable"] = {r: view(consumer, "get_claimable", [a]) for r, a in acc.items()}
    REC["final"] = final
    save()
    t = final["totals"]
    log(f"consumer balance {final['consumer_balance']} vs locked {t['locked']} + credited {t['credited']}")
    log(f"record written to {REC_PATH}")


if __name__ == "__main__":
    main()
