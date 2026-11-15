# MeterReader

A reusable GenLayer Intelligent Contract that turns one finished window of a public per-interval statistics table (hashrate per minute on a pool's worker page, messages per minute on a relay dashboard, any "value per time slot" table) into an on-chain reading that people and other contracts can rely on.

**Live on GenLayer Studio:** [`0x29762f9bce4F51e01696a947D24158c9C66B6636`](https://explorer-studio.genlayer.com/address/0x29762f9bce4F51e01696a947D24158c9C66B6636) (v2) · contract source: [`contracts/meter_reader.py`](contracts/meter_reader.py) · consumer example: [`examples/consumer/meter_consumer_example.py`](examples/consumer/meter_consumer_example.py) · MIT

## The problem

Two parties who meter something through a website (a hashrate rental, a node uptime deal, a usage-based payment) both look at the same public page, and neither can edit it. What they lack is a neutral way to turn "what the page showed for 06:10 to 06:15" into a record that pays out. Copying the numbers by hand puts trust in whoever copies them. Asking a model whether "the seller delivered" turns a number problem into an opinion.

MeterReader keeps the two jobs apart:

- **The model only copies.** Every validator renders the page and its model fills a fixed form with the rows inside the window. It is never asked to judge.
- **Code decides.** Plain Python turns each copied number and unit into an integer in a base unit, checks every row against the window and the slot grid, and decides the outcome kind.
- **Validators compare numbers, not prose.** They accept the leader's reading only if the outcome kind, the exact set of listed slots and every slot value agree within the meter's tolerance.

## How it works

1. `register_meter(url, source_name, series_name, value_label, unit_family, slot_minutes, unit_label, tolerance_bp, publish_lag_minutes)` stores a frozen meter:
   - `url`: the page (public addresses only; see *URL filter*).
   - `source_name`: the name the page must show, so a different site cannot stand in for it.
   - `series_name`, `value_label`: which series and which column to copy.
   - `unit_family`: `hashrate` (H/s up to EH/s, and Sol/s) or `count` (a plain number with an optional unit label).
   - `slot_minutes`: 1, 5, 10, 15, 30 or 60.
   - `tolerance_bp`: how far two validators' copies of one slot may differ, 0 to 500 basis points (default 100 = 1%).
   - `publish_lag_minutes`: 0 to 1440. For pages that post a slot's figure some minutes after the slot ends, this delays reading until the page has posted the last slot. Otherwise an early read would store that slot as missing.
2. `read(meter_id, window_start, slots)` opens one full slot after the window ends, plus the publishing lag, so every slot is final and posted on the page for every validator. Up to 96 slots.
3. The stored reading has one entry per slot. A slot the page does not list is stored as **missing**, not guessed.
4. `delivery_share_bp(reading_id, target_per_slot)` gives the capped pro-rata share of a target: each slot counts at most the target, and a missing slot counts as zero.
5. Anyone may read a window again. `get_window_readings(meter_id, window_start, slots)` lists every reading of one exact window: the first ten ids, the latest id and the count. A consumer can then apply a fixed rule, such as "the first READ" or "the latest reading".

### Outcomes

| Kind | When | Stored |
|---|---|---|
| `READ` | The page shows the series' table, times are UTC, every row in the window reads cleanly, and at least half of the window's slots are listed | Every slot (value or missing) and a summary: listed and missing slots, total, mean over all slots, min and max |
| `NOT_LISTED` | The page clearly says the series does not exist or has no data | No numbers. `delivery_share_bp` is 0 |
| `NO_READING` · `N1_PAGE_DARK` | Empty page, fetch error, maintenance page, another site (the source name is missing) or anything else | The reason only |
| `NO_READING` · `N2_FORMAT` | Times not in UTC, a row off the slot grid, a number or unit that cannot be read or does not fit the meter, the same slot twice with different values, or a model answer that is not a JSON object | The reason only |
| `NO_READING` · `C1_COVERAGE` | Fewer than half of the window's slots are on the page | The reason only |

`NO_READING` results are stored too: "the page was dark when it was read" is a fact other contracts may need, for example to apply a default rule.

## Why this equivalence check

GenLayer validators each run the non-deterministic step themselves and then decide whether to accept the leader's result. MeterReader's validator function:

1. **Re-validates the leader's result shape** (`_check_outcome`): known kind and reason, rows as `[slot, value]` integer pairs in increasing slot order inside the window, no rows on a `NOT_LISTED` result, and coverage at least 50%. A malformed or impossible leader result is rejected, never trusted.
2. **Reads the page itself** and compares (`_same_outcome`):
   - same kind (and the same reason for `NO_READING`);
   - the **same set of listed slots**, so a leader cannot drop an idle slot or invent one;
   - **every slot value within the tolerance**, relative to the larger value.

Per-slot comparison, not a comparison of totals, because consumers use the slots: a capped share, an outage excused in specific slots, a minimum per hour. A total-only check would let a leader move value from one slot to another.

**Worst case, stated plainly:** with tolerance *t*, a dishonest leader can shift each stored value by at most *t* of the larger value (1% by default), and cannot add, remove or move a slot. A consumer that needs exact copies registers the meter with `tolerance_bp = 0`.

Finished slots on a static page are identical for every validator. The tolerance absorbs rounding by different models, and pages that show the same value in another unit (6.05 GH/s against 6050 MH/s).

## State design

- `meters: TreeMap[str, Meter]`: each meter's specification, frozen as sorted JSON at registration, with its owner and creation time. There is no update method. To change a meter, register a new one.
- `readings: TreeMap[str, Reading]`: the agreed outcome (kind, reason, rows) only. The summary and the per-slot table are **derived on read** from the stored rows, so a stored figure can never disagree with the rows.
- `by_meter: TreeMap[str, str]`: the latest 200 reading ids per meter, for `get_readings`. Older readings stay readable by id.
- `by_window: TreeMap[str, str]`: for each exact window (`meter:start:slots`), the first ten reading ids, the latest id and the count. This is bounded, so repeated reads cannot grow one entry without limit.
- Integer base units (H/s, or millionths for `count`) are returned as decimal strings, so JavaScript clients do not lose precision.

## Guards

- **Prompt injection.** The page sits between markers and is labelled untrusted data. Page text that looks like a marker is removed, and each page is cut to 12,000 characters. Whatever the model returns, only `page_kind`, `source_name_on_page`, `times_utc` and up to 200 `rows` are read. Extra fields such as a "verdict" are ignored, and rows outside the window are skipped.
- **Units.** A row whose number and unit fields disagree (`"6.0 MH/s"` with unit `GH/s`) is a format error. So is a decimal comma (`6,28`), because it is ambiguous with a thousands separator. A row shown as `-` or `offline` is copied as a bare 0.
- **URL filter.** Only public names and public dotted IPv4 addresses are accepted. The filter refuses user info (`user@host`), backslashes, IPv6 literals, single-label hosts, numeric tricks (`2130706433`, `0x7f.0.0.1`, `0177.0.0.1`), private and reserved ranges, link-local addresses such as the cloud metadata address, and internal suffixes (`.local`, `.internal`, `.corp`, ...).
- **Time.** A reading cannot be taken before the window plus one full slot (plus the meter's publishing lag) has passed, so no slot is still in progress or unposted.

## Live results on Studio (14 Nov 2026, v2)

The examples use fictional pool pages hosted with the RigSettle demo (Fernhollow Pool, Quillmoor Pool and Examplecoin do not exist). Each page prints per-minute rows from the clock with a fixed formula, so every validator sees the same numbers for a finished minute. Each window is the last five finished minutes when the read was sent. The share is `delivery_share_bp` against a target of 10 GH/s. All runs come from [`tools/live_cases.py`](tools/live_cases.py) and are recorded in [`examples/live-runs.json`](examples/live-runs.json).

| Reading | Meter (fictional page) | Outcome | Values (GH/s per minute) | Share of 10 GH/s | Validators | Transaction |
|---|---|---|---|---|---|---|
| 1 | Fernhollow Pool · rig-sixty | READ | 6.15, 5.82, 6.23, 5.90, 6.01 | 60.22% | 3 agree | [0x56a5…633e](https://explorer-studio.genlayer.com/tx/0x56a5573483bebed78a48b502bcc1fb5dbd00c0909f20571f886b6cd8af25633e) |
| 2 | Fernhollow Pool · rig-steady | READ | 10.12, 9.88, 10.07, 10.00, 10.06 | 99.76% | 3 agree | [0x234f…8458](https://explorer-studio.genlayer.com/tx/0x234f516b24c748ba4ed731808b842ae7cd1371e9011979745d0a0fbc9ff88458) |
| 3 | Fernhollow Pool · rig-gappy (the pool leaves idle minutes out) | READ | 10.00, missing, 10.08, 9.90, missing | 59.80% | 3 agree | [0xe7bc…47c1](https://explorer-studio.genlayer.com/tx/0xe7bc681a1d9bf7dd1ba0f52b15dfda6ca6a1bd240a2e48515dfed663054747c1) |
| 4 | Fernhollow Pool · rig-ghost (page says the worker is not found) | NOT_LISTED | none | 0% | 3 agree | [0x3bc4…72be](https://explorer-studio.genlayer.com/tx/0x3bc4039c2ef3cdff07c9671ec36a4d9106edeb4925ef65e5032586eb7d1f72be) |
| 5 | Quillmoor Pool · rig-dark, read while its service was up | READ | 10.08, 9.96, 10.00, 9.98, 10.04 | 99.88% | 3 agree | [0x113c…88c4](https://explorer-studio.genlayer.com/tx/0x113c450ea86794b114e197c25db7a59d129e6202ccf35be631ff58b984a888c4) |
| 6 | Quillmoor Pool · rig-dark, read inside its down period (6 to 9 minutes past every ten) | NO_READING · N1_PAGE_DARK | none | | 3 agree | [0xe640…1d8b](https://explorer-studio.genlayer.com/tx/0xe640cc537ef51039795f2e9bea572284fc8e17dc9fe3a6686406b2bc0c331d8b) |

Reading 3 shows why a missing slot counts as zero. Averaging only the listed minutes would report 9.99 GH/s and pay in full for two minutes that never ran.

**Another contract relying on a reading (on chain).** [`MeterConsumerExample`](examples/consumer/meter_consumer_example.py) was deployed at [`0xdda671dF730E0fd3faFE4ED56b51B7a7Fa5529a6`](https://explorer-studio.genlayer.com/address/0xdda671dF730E0fd3faFE4ED56b51B7a7Fa5529a6), pointing at this MeterReader. Its `record_share("1", 10 GH/s)` call ([0x25c1…678c](https://explorer-studio.genlayer.com/tx/0x25c14085ba4bf49a13dbec0299d783e1a48ad74947e503ba11627f4737da678c)) read reading 1 and its share through `gl.get_contract_at(reader).view()` and stored 60.22% (S1_CAPPED_PRO_RATA). It read no web page and called no model. An escrow would use the same two calls and then pay by the share.

Meters 1 to 5 were registered from [`examples/`](examples/). **Also on Testnet Bradbury Phase 2:** [`0x83eD…6ab5`](https://scan.bradbury.genlayer.com/address/0x83eDE0d5CE027E9C8e34F4bcB070540cAa0C6ab5), with every live case repeated there by 5 validators (rig-gappy 59.68% with two missing slots, the dark page refused in its down period, the consumer reading on chain); see [`../bradbury/README.md`](../bradbury/README.md#meterreader-on-bradbury).

Deployment: [`deployment.json`](deployment.json). The first version (`0xF85Bc3858068958C8682b2fbB5f668FBc867776a`, the repository's first commit) had no publishing lag and no window index. It is superseded and not used.

## Use it

From the command line (Studio, test GEN only; `MR_KEY` is a throwaway key, and without it a temporary funded account is made):

```bash
python3 -m venv venv && venv/bin/pip install -r ../requirements.txt
venv/bin/python tools/mr.py register examples/fernhollow-rig-sixty.json   # prints the meter id
venv/bin/python tools/mr.py read 1 5                                       # last five finished minutes
venv/bin/python tools/mr.py show <reading_id>
venv/bin/python tools/mr.py share <reading_id> 10000000000                 # target 10 GH/s, in H/s
```

From an app (genlayer-js or genlayer-py), call the views:

- `get_meter(meter_id)`, `get_reading(reading_id)`, `get_readings(meter_id, limit)`, `get_latest_readings(limit)`, `get_window_readings(meter_id, window_start, slots)`;
- `delivery_share_bp(reading_id, target_per_slot)`;
- `get_counts()` and `get_rules()` (every constant a reading is held to).

From another Intelligent Contract:

```python
reader = gl.get_contract_at(Address(METER_READER)).view()
reading = reader.get_reading(reading_id)            # check meter_id, window_start and slots are the ones you agreed
share = reader.delivery_share_bp(reading_id, str(target_per_slot))["share_bp"]   # 0..10000
```

This is the pattern [`MeterConsumerExample`](examples/consumer/meter_consumer_example.py) runs live (above). A consumer should check that the reading is for the meter and window it expects, and decide in advance which reading of a window counts, using `get_window_readings`.

To adapt it to a new kind of page, register a meter. The contract itself does not change: `source_name`, `series_name` and `value_label` tell the model what to copy, and the unit family tells the code how to read it.

## Tests

```bash
cd meter-reader
PYTHONPATH=. ../venv/bin/pytest tests/direct -q        # 145 direct-mode tests, web and model mocked
PYTHONPATH=. ../venv/bin/python tools/mutate.py        # 53 of 53 mutants caught
../venv/bin/genvm-lint check contracts/meter_reader.py
MR_KEY=<throwaway key> ../venv/bin/python tools/live_cases.py --deploy   # redo the live table on Studio
```

`tools/mutate.py` breaks the contract on purpose, one change at a time (53 changes: limits, timing, interpretation, units, leader checks, agreement, consumer figures, URL filter, prompt guards), and confirms the tests catch every one.

The tests cover:
- registration rules, including 17 URL-filter cases;
- every outcome kind and reason;
- unit normalisation and count meters;
- 5-minute slots and timing;
- injection, through a page that tries to close the data block and through model answers that add fields or rows;
- views and caps, the publishing lag and the window index;
- validator agreement and rejection: tolerance edges, a different slot set, a different kind or reason, a leader error, and 15 malformed leader results;
- the shape guard on its own (19 malformed results), which is also applied to the agreed result before it is stored.

## Limits

- A reading is what one public page showed for one finished window. If the site itself reports wrong numbers, the reading is wrong in the same way. MeterReader removes the copying party from the trust chain, not the site.
- Pages that need a login, a click or more than about four seconds of script time cannot be read.
- Rows must carry UTC times on the slot grid. Pages in local time give `N2_FORMAT` by design.
- If validators read a page while it is posting a slot (a meter registered without enough publishing lag), their slot sets differ and no reading is agreed. Nothing wrong is stored, but the read must be repeated later.
- Studio validators run different models. If a page's layout is ambiguous, validators may disagree, and the transaction then rotates to a new leader or ends undetermined. No wrong number is stored in that case.

## Versions

- Contract runner `py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6` (the header of the contract file).
- Test tooling pinned to exact commits in [`../requirements.txt`](../requirements.txt): genlayer-test 0.29.2, genvm-linter 0.11.1-rc.2, genlayer-py 0.18.0.
