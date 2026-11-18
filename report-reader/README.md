# ReportReader

A reusable GenLayer Intelligent Contract that turns a company's published periodic report into **exact on-chain figures** that other contracts can use: revenue for an earn-out, EBITDA and debt for a covenant test, net asset value for a performance fee. The figures are data, not code: anyone registers a report with the figures they need, and each period's report has **one official reading**.

**Live on GenLayer Studio:** see [Live results](#live-results-on-studio) · contract: [`contracts/report_reader.py`](contracts/report_reader.py) · consumer example: [`examples/consumer/earn_out_example.py`](examples/consumer/earn_out_example.py) · MIT

## The problem

Earn-outs, covenant tests, performance fees and revenue shares all pay on a few figures in a report the company publishes every period. Today someone reads the report and keys the numbers in by hand. Mistakes, delays and "what the report says" arguments all happen at that step, and a contract that wants to pay on the figure has no way to read it.

Asking a model "did the company hit its target?" turns a number into an opinion. ReportReader keeps the jobs apart:

- **The model only copies.** Every validator renders the page, and its model fills a fixed form: each figure's value exactly as printed, its scale and the words that state the scale, its line label, and whether the page shows it more than once.
- **Code decides.** Plain Python checks every copy against the frozen report and against the validator's own copy of the page, converts with integers only, and rounds once in the direction the report's owner chose.
- **Validators agree exactly.** They accept the leader's reading only if the outcome kind, the reason code and every figure are identical to their own.

## How it works

1. **Register** a frozen report with `register_report(spec_json)`:

   | Field | Meaning |
   |---|---|
   | `issuer_name` | The company name the page must show (compared as whole words). |
   | `url_template` | The page address with `{n}` for the period number, in the path. Public hosts only; no query or fragment. |
   | `currency` | An ISO code from `get_rules()`. |
   | `period_ends` | 1 to 24 times, `YYYY-MM-DD HH:MM` in UTC, strictly increasing. |
   | `publish_lag_minutes` | When a period's report is due after its end; its reading window opens then. Real reports: weeks. |
   | `read_window_minutes` | How long the window stays open (at least 30). |
   | `figures` | 1 to 8 figures (below). |

   Each figure has a `key`, a short `label_hint` for the model, a **closed list of `labels`** (1 to 6 line labels it may be printed under), `ltm` (must the page label it as the last twelve months?), `decimals` (stored units are 10^-decimals of a currency unit), `step` (a power of ten in stored units), `rounding` (`down` or `up`, so the user picks the cautious side) and `sign`:
   - `as_printed`: brackets or a minus sign mean negative;
   - `magnitude`: the absolute value (debt printed in brackets);
   - `finance_cost`: net finance cost positive, net finance income negative, decided from the line's own label by the rule PrivateCreditGate's four reviews shaped (see the contract).

   The specification is stored as canonical JSON with its **sha256 digest**. A consumer pins the report id **and** the digest. Nothing can be changed later: register a new report instead.

2. **Read** with `read(report_id, n)` during period `n`'s window. Anyone may call it. A call before the window opens is refused. The first `READ` in the window is the period's **official reading**; nothing replaces it.
3. **Consume** with `get_reading(report_id, n, at)`, passing the consumer's own time. It returns one of:

   | Status | Meaning | Final? |
   |---|---|---|
   | `NOT_DUE` | The period has not ended. | no |
   | `WAITING` | Ended; the report is not due yet (publishing lag). | no |
   | `OPEN` | The reading window is open and has no `READ` yet. | no |
   | `CLOSING` | The window has closed, but no write stamped at or after the close has been processed yet, so a `READ` stamped before it could still land. Anyone may call `tick(report_id)`. | no |
   | `READ` | The official reading, with every figure as a decimal string in its stored units. | **yes** |
   | `MISSING` | The window closed with no `READ`. | **yes** |

   `READ` and `MISSING` never change once reached, for any consumer.

### Outcomes of a reading

| Kind | When |
|---|---|
| `READ` | Every figure read cleanly. Stored and binding if it is the first in the window. |
| `NOT_PUBLISHED` | The page clearly says the period's report is not published yet. Recorded; binds nothing. |
| `NO_READING` · `N1_PAGE_DARK` / `N1_WRONG_PAGE` | Empty page or fetch error; another company, only other periods, an error or login page. |
| `NO_READING` · `N3_NOT_FINAL` | The figures are marked draft, preliminary, estimated or subject to change. |
| `NO_READING` · `N2_WRONG_PERIOD` / `N2_CURRENCY` | The period end (to the minute, UTC) or the currency does not match. |
| `NO_READING` · `N2_LABEL` | A figure's copied line label is not on its closed list. |
| `NO_READING` · `N2_NOT_ANCHORED` | The copied label is not printed on the validator's own copy of the page, or the copied value does not follow it within 160 characters as a whole number. |
| `NO_READING` · `N2_UNITS_MISSING` | No scale, or the scale words are not printed, or they name another scale. |
| `NO_READING` · `N2_CONFLICT` / `N2_NOT_LTM` / `N2_FIGURE_MISSING` / `N2_FINANCE_LABEL` | Two candidate figures; an LTM figure not labelled LTM; a missing figure; a finance-cost label the sign rule cannot read. |
| `NO_READING` · `N2_FORMAT` | An ambiguous number (`12.450`, `6,28`, `40'000`, an exponent, a JSON float), a page with decimal commas, or a model answer that is not a JSON object. Refused, never guessed. |

Attempts are counted without limit; the first 20 are kept with their outcome.

## Why this equivalence check

GenLayer validators each run the non-deterministic step and decide whether to accept the leader's result. ReportReader's validator function first re-checks the leader's result shape (`_check_outcome`: known kind and reason, exactly the report's figure keys, each an integer that is a whole multiple of its step, magnitudes not negative), then reads the page itself and compares (`_same_outcome`) **exactly**: the kind, the reason of a `NO_READING`, and every figure.

**Exact, not a tolerance.** A GenLayer steward rejected an earlier contract of ours (MeterReader v1) because validators accepted values within a tolerance and the leader's values were stored, so two acceptable readings could pay a consumer differently. Here each figure is rounded once, to the report's step, before comparison; two copies that differ only below the step store the same number and agree, and any other difference means no agreement. Nothing a leader chooses can move a stored figure.

**Anchored copying (new).** Agreement among models is not enough on its own: several models can make the same mistake. So code checks each copy against the validator's **own** rendering of the page: the copied line label must be on the figure's closed list **and** printed on the page, the copied value must follow that label within 160 characters as a whole number (`1,000` does not match inside `21,000` or `1,000.5`), and the words that state the scale must be printed and name the copied scale and no other. A figure the model invents, takes from another row, or scales wrongly is refused before validators even compare.

**One official reading, and a clock that never runs backwards.** Every write to a report moves its clock to the transaction's time if that is later, and a reading is handled at the clock's time. Once any write stamped at or after a window's close has been processed, no `READ` can land in that window; until then `get_reading` says `CLOSING`. So `READ` and `MISSING` are final for every consumer, whatever order the network processes transactions in.

## State design

- `reports: TreeMap[str, Report]`: the canonical specification, its digest, owner and creation time.
- `clocks: TreeMap[str, u256]`: each report's clock.
- `periods: TreeMap[str, str]`: per `report:period`, the official reading (time, reader, page, attempt number and figures) and the first 20 attempts with the count.
- Figures are integers in stored units, returned as decimal strings so JavaScript clients do not lose precision.

## Guards

- **Prompt injection.** The page sits between markers and is labelled untrusted data; marker-like text is removed and the page is cut to 12,000 characters. Only the fixed form's fields are read. Anchoring means an injected instruction cannot make a validator store a number the page does not print next to its label.
- **URL filter.** Public names and public dotted IPv4 addresses only; no user info, backslashes, IPv6 literals, single-label hosts, numeric tricks, private or link-local ranges, or internal suffixes. `{n}` must be in the path.
- **Time.** A reading is refused before its window opens. A call stamped after the close reads nothing and settles the period.

## Live results on Studio

Run `s1`, 18 Nov 2026, on GenLayer Studio, with the fictional pages at `https://privatecredit.brilliantnodes.com/report-reader/s1/` ([`tools/make_pages.py`](tools/make_pages.py), served by a sister project's GitHub Pages site). Script: [`tools/live.py`](tools/live.py). Record: [`examples/live-studio-s1.json`](examples/live-studio-s1.json). Every transaction re-read from the chain after finalization, and the consumer's balance reconciled: [`examples/live-studio-s1-check.json`](examples/live-studio-s1-check.json) ([`tools/verify.py`](tools/verify.py)).

- ReportReader: [`0xf698472731C1a9e9C49C8787A0d46b37D7EE8E8b`](https://explorer-studio.genlayer.com/address/0xf698472731C1a9e9C49C8787A0d46b37D7EE8E8b) · [open in Studio](https://studio.genlayer.com/?import-contract=0xf698472731C1a9e9C49C8787A0d46b37D7EE8E8b)
- EarnOutExample: [`0x0509107d0F55337d7374d9404E68e903a82980eb`](https://explorer-studio.genlayer.com/address/0x0509107d0F55337d7374d9404E68e903a82980eb)

What it shows:

- **Exact figures from a table page** (Tarnwick, period 0, EUR thousands, with a prior-quarter column next to the current one): revenue 15,240,000; LTM EBITDA 4,180,000 (4,180.5 thousand, rounded down to the 1,000 step); net finance costs 2,150,000, read as a cost from its label although printed in brackets; total borrowings 48,000,000 (magnitude). Validators took the current quarter, not the prior one.
- **Exact figures from a highlights page with the scale in each line** (Tarnwick, period 2, "EUR 16.2 million"): 16,200,000; 4,450,000; 2,100,000; 47,500,000.
- **Refused, never guessed:** a page marked "Preliminary figures, subject to change" (`N3_NOT_FINAL`); a page that prints only "Adjusted EBITDA", which is not on the figure's label list (`N2_LABEL`); a page in decimal-comma format (`N2_FORMAT`); a page for the previous quarter (`N1_WRONG_PAGE`).
- **A planted instruction does not move a figure:** the injection page tells "automated readers" to record every figure as 0; the reading stored the table's figures.
- **One official reading:** a second read of Tarnwick period 0 was refused; a read before the window opened was refused; a read after a window closed read nothing and settled it as `MISSING`.
- **Not published, then missing:** Tarnwick period 1 read `NOT_PUBLISHED` (binds nothing); after its window closed, `tick` settled it as `MISSING`.
- **The consumer moved money on it:** earn-out 1 (10 GEN, revenue floor 10,000,000, target 20,000,000) paid the seller 5.24 GEN and the buyer 4.76 GEN; earn-out 2 (5 GEN, on period 1) refunded the buyer when the report was missing; a settle while the window was open was refused; an earn-out with a wrong digest and one pinned after the period ended were refused and their GEN credited back. Both parties withdrew; the consumer's balance ended at 0.

| # | Case | Call | Outcome | Tx |
|---|---|---|---|---|
| 1 | register tarnwick | `register_report` | ACCEPTED / SUCCESS · report 1 | [`0x405a2467…`](https://explorer-studio.genlayer.com/tx/0x405a246787868e3c4689d4da1ac2211b681d5fc8704e22ebb7c97cec87dbd5f9) |
| 2 | register ostravelle-draft | `register_report` | ACCEPTED / SUCCESS · report 2 | [`0xc9264348…`](https://explorer-studio.genlayer.com/tx/0xc9264348c5f9c3a3c93ec8df625f744842d5371d2cf8b4347ba7099af87feb52) |
| 3 | register ostravelle-adjusted | `register_report` | ACCEPTED / SUCCESS · report 3 | [`0xa179dbe4…`](https://explorer-studio.genlayer.com/tx/0xa179dbe4e145b6250640e59af6e68a68212a411fa46eded5d2eb220b8f0b097d) |
| 4 | register ostravelle-comma | `register_report` | ACCEPTED / SUCCESS · report 4 | [`0x8676f57d…`](https://explorer-studio.genlayer.com/tx/0x8676f57d41a296bf4f46846361354b15fa3b279c0ac8cd1f0e3f291b80eb2b3d) |
| 5 | register ostravelle-injection | `register_report` | ACCEPTED / SUCCESS · report 5 | [`0x9724ade3…`](https://explorer-studio.genlayer.com/tx/0x9724ade302aaf869cff0838691b15d0fda925f209990105461da0c773f96d5bf) |
| 6 | register ostravelle-old | `register_report` | ACCEPTED / SUCCESS · report 6 | [`0x60318e24…`](https://explorer-studio.genlayer.com/tx/0x60318e248e5886fe0e3d0524e6a292eceacfe9a7c3824eb6295d4520d37572d4) |
| 7 | read before the window opens (refused) | `read` | ACCEPTED / ERROR · period 0's reading window opens at 2026-11-18 08:20 UTC | [`0x4b26c08d…`](https://explorer-studio.genlayer.com/tx/0x4b26c08dcc67f3a71d424ddaed6c2f2d9aeb1b6868264a374bed80ef6cb2e2cd) |
| 8 | earn-out 1: revenue, floor 10,000,000, target 20,000,000 | `create` | ACCEPTED / SUCCESS · escrowed 10.0 GEN | [`0x096e8ca3…`](https://explorer-studio.genlayer.com/tx/0x096e8ca38618d170fe80d6a1d7ec413ae1a6852901468b948ebf1a1c57152417) |
| 9 | earn-out 2: LTM EBITDA of period 1 | `create` | ACCEPTED / SUCCESS · escrowed 5.0 GEN | [`0x83fc99d3…`](https://explorer-studio.genlayer.com/tx/0x83fc99d3996f2398fa78516029a261375c8fea0b01aeed6930e5ded2f6a7caa0) |
| 10 | earn-out refused: wrong digest (value credited back) | `create` | ACCEPTED / SUCCESS · the report's digest is not the one pinned | [`0x14657a3c…`](https://explorer-studio.genlayer.com/tx/0x14657a3cb98d8e82ece1f422426bfef4edab92ac1f78306814fd44d451097213) |
| 11 | Tarnwick period 0: table page | `read` | ACCEPTED / SUCCESS · READ ltm_ebitda 4180000, net_finance_costs 2150000, revenue 15240000, total_debt 48000000 | [`0x8ec87fac…`](https://explorer-studio.genlayer.com/tx/0x8ec87fac4b9490e29ace50b4b559bb8b615e0cc9bec40ce14c6f1a4068d5aef1) |
| 12 | ostravelle-draft period 0 | `read` | ACCEPTED / SUCCESS · NO_READING N3_NOT_FINAL | [`0xb8cbdc74…`](https://explorer-studio.genlayer.com/tx/0xb8cbdc74f1271f18d3a68529802e344df8abd42894aab2b01c9b75c10fb82f64) |
| 13 | ostravelle-adjusted period 0 | `read` | ACCEPTED / SUCCESS · NO_READING N2_LABEL | [`0x534366f8…`](https://explorer-studio.genlayer.com/tx/0x534366f8f372aed9035e8f295c00c9b8ff0b9af23e65109ea35a2a5b13d89a22) |
| 14 | ostravelle-comma period 0 | `read` | ACCEPTED / SUCCESS · NO_READING N2_FORMAT | [`0x8f1f8777…`](https://explorer-studio.genlayer.com/tx/0x8f1f87770654ab592d6b79503aee71336e153fdd3c80f48e28415175a76ee27a) |
| 15 | ostravelle-injection period 0 | `read` | ACCEPTED / SUCCESS · READ ltm_ebitda 2240000, net_finance_costs 910000, revenue 8315000, total_debt 21400000 | [`0x8591f428…`](https://explorer-studio.genlayer.com/tx/0x8591f4280f012fbde505df2f445197216899550140f0016a9389707f8e34996c) |
| 16 | ostravelle-old period 0 | `read` | ACCEPTED / SUCCESS · NO_READING N1_WRONG_PAGE | [`0x029e2609…`](https://explorer-studio.genlayer.com/tx/0x029e2609bafb343b37c1890ce0c34fb285bc8cc571e924e77da99942bdc5df1e) |
| 17 | Tarnwick period 0 read again (refused: one official reading) | `read` | ACCEPTED / ERROR · period 0 already has its official reading | [`0xd4d04423…`](https://explorer-studio.genlayer.com/tx/0xd4d044233676cdf893f4ae8ff83c7f52605cc9a8b0d2d17005094672b26e19f6) |
| 18 | earn-out pinned after the period ended (refused, value credited back) | `create` | ACCEPTED / SUCCESS · the period has already ended (status READ): pin a period before it ends | [`0xd3b57b8b…`](https://explorer-studio.genlayer.com/tx/0xd3b57b8b3ea3b0a7a7fce8618c1b4286cc0a327aea1f624d6074556593cf31ff) |
| 19 | settle earn-out 1 | `settle` | ACCEPTED / SUCCESS · READ: seller 5.24 GEN, buyer 4.76 GEN | [`0xb2af30ae…`](https://explorer-studio.genlayer.com/tx/0xb2af30ae41df7f27ecf25fd17e2aa1c022647485c867670510bd94bacde1cd99) |
| 20 | Tarnwick period 1: not yet published | `read` | ACCEPTED / SUCCESS · NOT_PUBLISHED | [`0xa553b912…`](https://explorer-studio.genlayer.com/tx/0xa553b912ed566a9cd9f20068e0badcdfd98e8df500a109aba22eb968a5781a30) |
| 21 | settle earn-out 2 too early (refused) | `settle` | ACCEPTED / ERROR · no final answer yet (status OPEN) | [`0xacbe1384…`](https://explorer-studio.genlayer.com/tx/0xacbe1384ff1f35938f7ad79b3a0e24aa01f7213414558847336a4a3ec17778c8) |
| 22 | Tarnwick period 2: highlights page in millions | `read` | ACCEPTED / SUCCESS · READ ltm_ebitda 4450000, net_finance_costs 2100000, revenue 16200000, total_debt 47500000 | [`0x48ddf128…`](https://explorer-studio.genlayer.com/tx/0x48ddf128d3544d5746a374eba82a1543bebcdffdde0eb20ca9d7b56d9423d5fa) |
| 23 | ostravelle-draft read after its window closed | `read` | ACCEPTED / SUCCESS · CLOSED → MISSING | [`0x090c34d8…`](https://explorer-studio.genlayer.com/tx/0x090c34d84eac2592637cd4c59ef3a74e7b46128ee6bafadb7d3bc7cb8402c4f8) |
| 24 | tick Tarnwick: period 1 settles as MISSING | `tick` | ACCEPTED / SUCCESS · missing [1] | [`0xdedc3fb9…`](https://explorer-studio.genlayer.com/tx/0xdedc3fb95bce2ac7b7cf1292949062009d09a78bbb3de50bf292d18c9a750df0) |
| 25 | settle earn-out 2 (report missing: buyer refunded) | `settle` | ACCEPTED / SUCCESS · MISSING: seller 0 GEN, buyer 5 GEN | [`0x827ad1bf…`](https://explorer-studio.genlayer.com/tx/0x827ad1bf81e4acf8488b9abe60db32919f13928a2f06edf58914542b1a4c8354) |
| 26 | withdraw (bob) | `withdraw` | ACCEPTED / SUCCESS · withdrew 5.24 GEN | [`0x746a6900…`](https://explorer-studio.genlayer.com/tx/0x746a6900e17099347dba9bf6bdaa874d1e99c2a4468e1d7a13326b4ea4cef7c8) |
| 27 | withdraw (alice) | `withdraw` | ACCEPTED / SUCCESS · withdrew 11.76 GEN | [`0x81826b59…`](https://explorer-studio.genlayer.com/tx/0x81826b594fb041e0eb34818b055498e6e0737254ccfc4eb73d7b143c0d679955) |

## EarnOutExample: a consumer that moves money

[`examples/consumer/earn_out_example.py`](examples/consumer/earn_out_example.py) is a deferred payment paid on a reported figure. It reads no page and calls no model.

1. The buyer calls `create` (payable) before the period ends and pins the seller, a report id **and its digest**, the period, a figure, a floor and a target. The contract checks all of it against ReportReader with a cross-contract view: the digest must match, the figure and period must exist, and the status must still be `NOT_DUE`, so the outcome is unknown when the money goes in. A refused `create` credits the GEN back instead of reverting.
2. After the answer is final, anyone calls `settle`: on `READ`, the seller gets the escrow on a straight line from the floor (nothing) to the target (everything), rounded down, and the buyer the rest; on `MISSING`, the buyer gets everything back. Any other status refuses (`CLOSING` says to send `tick` first).
3. Payouts are credits; each address takes its own with `withdraw()`. `totals()` reconciles the contract's balance as `locked + credited`.

## Tests

```bash
python3 -m venv venv && venv/bin/pip install -r requirements.txt
cd report-reader
PYTHONPATH=. ../venv/bin/pytest tests/direct -q                  # 210 tests (168 ReportReader, 42 EarnOutExample)
PYTHONPATH=. ../venv/bin/python tools/mutate.py                   # 85 of 85 mutants caught (69 reader, 16 consumer)
../venv/bin/genvm-lint check contracts/report_reader.py
../venv/bin/genvm-lint check examples/consumer/earn_out_example.py
```

The direct VM cannot make cross-contract calls, so EarnOutExample's `create` (after its first checks) and `settle` are tested through their pure functions and proven live. The same test files pass on GenVM v0.6 against the Bradbury builds made by [`../bradbury/port.py`](../bradbury/port.py) (`bradbury/build/report_reader.py`, `bradbury/build/earn_out_example.py`), with genlayer-test 0.30.0rc2 and [`../bradbury/tests/conftest_v6.py`](../bradbury/tests/conftest_v6.py).

## Limits

- **Trust in the published figures and in the host.** A reading says what one public page showed. It trusts the issuer's figures, as a printed report does; whoever controls the page's host controls what is read. Pin the issuer's own investor-relations host.
- **The closed label list is not a parser.** It stops a figure being taken from a line the user did not name, but a listed label can also occur inside a longer line (`Revenue` inside `Other revenue`). List exact labels and avoid short ones that occur inside others.
- **Layouts.** Anchoring needs the value printed within 160 characters after its label. Tables with labels in one column and values in the next row, or values far from their labels, give `N2_NOT_ANCHORED`: nothing wrong is stored, but nothing is read.
- **Who reads first** fixes the moment of the official reading within the window. A `NOT_PUBLISHED` attempt binds nothing, so anyone may read again when the report appears.
- **Appeals** re-read the page as it then stands.
- **Timestamps and rendering.** A reading's time is its transaction's timestamp, and windows and the report clock use it. Validators render the page when the transaction is processed, which on a busy network can be minutes later (up to about 4 minutes on Studio in the live run, when reads queued).
- **The demo** compresses a reporting year into minutes and states each period end to the minute; real reports use dates (a date is accepted for a period that ends at midnight UTC). The demo pages are fictional and hosted on a sister project's site.

## Versions

- v1 (this): reusable reports with up to 8 figures, closed label lists, anchored copying, exact agreement, one official reading per period, a monotonic report clock and a money-moving consumer.

Every company, page and figure in this folder is fictional. Test GEN only.
