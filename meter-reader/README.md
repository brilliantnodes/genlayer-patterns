# MeterReader

A reusable GenLayer Intelligent Contract that turns one finished window of a public per-interval statistics table (hashrate per minute on a pool's worker page, messages per minute on a relay dashboard, any "value per time slot" table) into an on-chain reading that people and other contracts can rely on.

**Live on GenLayer Studio:** [`0xa0FE27774c2f1F0d35bd83dA806cFB1F85F4209C`](https://explorer-studio.genlayer.com/address/0xa0FE27774c2f1F0d35bd83dA806cFB1F85F4209C) (v3: exact agreement, one official reading per window) · contract source: [`contracts/meter_reader.py`](contracts/meter_reader.py) · consumer example: [`examples/consumer/meter_consumer_example.py`](examples/consumer/meter_consumer_example.py) · MIT

## The problem

Two parties who meter something through a website (a hashrate rental, a node uptime deal, a usage-based payment) both look at the same public page, and neither can edit it. What they lack is a neutral way to turn "what the page showed for 06:10 to 06:15" into a record that pays out. Copying the numbers by hand puts trust in whoever copies them. Asking a model whether "the seller delivered" turns a number problem into an opinion.

MeterReader keeps the two jobs apart:

- **The model only copies.** Every validator renders the page and its model fills a fixed form with the rows inside the window. It is never asked to judge.
- **Code decides.** Plain Python turns each copied number and unit into an integer in a base unit, checks every row against the window and the slot grid, and decides the outcome kind.
- **Validators compare numbers, not prose, and exactly.** They accept the leader's reading only if the outcome kind, the set of listed slots and every stored value are identical to their own. So every accepted reading of a page stores the same numbers, and every figure derived from it, such as `delivery_share_bp` for any target, is the same whichever validators accepted it.

## How it works

1. `register_meter(url, source_name, series_name, value_label, unit_family, slot_minutes, unit_label, resolution, publish_lag_minutes, read_within_minutes)` stores a frozen meter:
   - `url`: the page (public addresses only; see *URL filter*).
   - `source_name`: the name the page must show, so a different site cannot stand in for it.
   - `series_name`, `value_label`: which series and which column to copy.
   - `unit_family`: `hashrate` (H/s up to EH/s, and Sol/s) or `count` (a plain number with an optional unit label).
   - `slot_minutes`: 1, 5, 10, 15, 30 or 60.
   - `resolution`: every copied value is rounded **down** to a whole multiple of this many base units before it is compared and stored (default 1, i.e. exact; for example `10000000` stores hashrate in steps of 0.01 GH/s). It is a step, not a tolerance: two copies agree only if they round to the same stored number.
   - `publish_lag_minutes`: 0 to 1440. For pages that post a slot's figure some minutes after the slot ends, this delays reading until the page has posted the last slot. Otherwise an early read would store that slot as missing.
   - `read_within_minutes`: 5 to 1440 (default 60). The **read period**: a window can be read only from the moment reading opens until this many minutes later. It should be shorter than the time the page keeps a window's rows.
2. `read(meter_id, window_start, slots)` opens one full slot after the window ends, plus the publishing lag, so every slot is final and posted on the page for every validator, and closes `read_within_minutes` later. Up to 96 slots.
3. The stored reading has one entry per slot. A slot the page does not list is stored as **missing**, not guessed.
4. **One window, one answer, taken while the page still shows it.** The first conclusive reading (`READ` or `NOT_LISTED`) of a window in its read period is its **official reading**, and the window cannot be read again after it. A `NO_READING` leaves the window open, so anyone may try again until the period closes. Without this, a window read twice (say, once while every row was on the page and again after old rows scrolled off or the pool dropped the worker) could have two accepted readings that pay differently, and a consumer could pick one; and without the read period, whoever read first could wait for that moment. **Stated plainly:** within the read period, whoever reads first fixes the moment of the official reading. Anyone, including either party to a deal, may read as soon as the period opens, and nobody can replace that result later. If the period closes with no conclusive reading, the window has none, and a consumer applies its own default.
5. `window_share_bp(meter_id, window_start, slots, target_per_slot)` gives the capped pro-rata share of a target from the official reading (each slot counts at most the target, and a missing slot counts as zero); `get_window_reading` returns the official reading itself. `delivery_share_bp(reading_id, target_per_slot)` gives the same figure for a reading id, and `get_window_readings` lists a window's official id, its first ten ids (including `NO_READING` attempts), the latest id and the count.

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
2. **Reads the page itself** and compares (`_same_outcome`), **exactly**:
   - same kind (and the same reason for `NO_READING`);
   - the **same set of listed slots**, so a leader cannot drop an idle slot or invent one;
   - the **same stored value in every slot**, after each copy is rounded down to the meter's `resolution`.

Per-slot comparison, not a comparison of totals, because consumers use the slots: a capped share, an outage excused in specific slots, a minimum per hour. A total-only check would let a leader move value from one slot to another.

**Why exact, not a tolerance (changed in v3).** v2 accepted copies within 1% per slot and stored the leader's values. A GenLayer steward rejected that: two readings validators would both accept could give a consumer different allocations (for example a different `delivery_share_bp`), and the leader chose which one was stored. Rounding to a fixed resolution and then requiring equality removes that freedom: every accepted reading of a page holds the same numbers, and a leader cannot move any stored value. An independent review then pointed out the same problem spread over time (one window read again later, after the page changed), so each window now has one official reading (see *How it works*). A second review pointed out that whoever reads first still chose the moment, and could wait until rows had scrolled off; so reading is now possible only in a short read period right after the window. Together: every consumer that agreed a meter, a window and a target gets the same share, from one reading taken while the page still showed the window. `window_share_bp` also refuses a target that is not a whole multiple of the resolution, since stored values are multiples of it and such a target could never be met in full.

**The cost, stated plainly:** consensus is stricter. Finished slots on a static page are identical for every validator, and the same value written in another unit (6.05 GH/s against 6050 MH/s) converts to the same integer, so this costs nothing on clean pages (all live readings below were agreed 3 of 3). If models copy different digits, or two copies straddle a resolution step, the reading gets **no agreement**: nothing is stored, and anyone may read the window again. Nothing wrong is ever stored. A meter can choose a coarser `resolution` to absorb trailing digits it does not care about.

## State design

- `meters: TreeMap[str, Meter]`: each meter's specification, frozen as sorted JSON at registration, with its owner and creation time. There is no update method. To change a meter, register a new one.
- `readings: TreeMap[str, Reading]`: the agreed outcome (kind, reason, rows) only. The summary and the per-slot table are **derived on read** from the stored rows, so a stored figure can never disagree with the rows.
- `by_meter: TreeMap[str, str]`: the latest 200 reading ids per meter, for `get_readings`. Older readings stay readable by id.
- `by_window: TreeMap[str, str]`: for each exact window (`meter:start:slots`), the official reading id, the first ten reading ids, the latest id and the count. This is bounded, so repeated attempts cannot grow one entry without limit.
- Integer base units (H/s, or millionths for `count`) are returned as decimal strings, so JavaScript clients do not lose precision.

## Guards

- **Prompt injection.** The page sits between markers and is labelled untrusted data. Page text that looks like a marker is removed, and each page is cut to 12,000 characters. Whatever the model returns, only `page_kind`, `source_name_on_page`, `times_utc` and up to 200 `rows` are read. Extra fields such as a "verdict" are ignored, and rows outside the window are skipped.
- **Units.** A row whose number and unit fields disagree (`"6.0 MH/s"` with unit `GH/s`) is a format error. So is a decimal comma (`6,28`), because it is ambiguous with a thousands separator. A row shown as `-` or `offline` is copied as a bare 0.
- **URL filter.** Only public names and public dotted IPv4 addresses are accepted. The filter refuses user info (`user@host`), backslashes, IPv6 literals, single-label hosts, numeric tricks (`2130706433`, `0x7f.0.0.1`, `0177.0.0.1`), private and reserved ranges, link-local addresses such as the cloud metadata address, and internal suffixes (`.local`, `.internal`, `.corp`, ...).
- **Time.** A reading cannot be taken before the window plus one full slot (plus the meter's publishing lag) has passed, so no slot is still in progress or unposted, nor after the meter's read period, so nobody can wait until the page has dropped the window's rows.

## Live results on Studio (16 Nov 2026, v3)

The examples use fictional pool pages hosted with the RigSettle demo (Fernhollow Pool, Quillmoor Pool and Examplecoin do not exist). Each page prints per-minute rows from the clock with a fixed formula, so every validator sees the same numbers for a finished minute. Each window is the last five finished minutes when the read was sent. The share is `delivery_share_bp` against a target of 10 GH/s. Meters use `resolution` 1 (exact base units) and a 60-minute read period. All runs come from [`tools/live_cases.py`](tools/live_cases.py) and are recorded in [`examples/live-runs.json`](examples/live-runs.json).

| Reading | Meter (fictional page) | Outcome | Values (GH/s per minute) | Share of 10 GH/s | Validators | Transaction |
|---|---|---|---|---|---|---|
| 1 | Fernhollow Pool · rig-sixty | READ | 5.73, 5.90, 5.86, 6.29, 5.87 | 59.30% | 3 of 3, exact | [0x334a…7908](https://explorer-studio.genlayer.com/tx/0x334abd8c361d0e0a77ea0bfcfe6e3fe83a5b37d6ac5a6d36337dffe41ab17908) |
| 2 | Fernhollow Pool · rig-steady | READ | 10.08, 10.10, 9.86, 10.11, 10.04 | 99.72% | 3 of 3, exact | [0xefed…eac6](https://explorer-studio.genlayer.com/tx/0xefed3ae7a9b6174e6ee15e8df2eb728592492e53498a9c30ce080cc13f6beac6) |
| 3 | Fernhollow Pool · rig-gappy (the pool leaves idle minutes out) | READ | 9.94, 9.93, missing, 9.93, missing | 59.60% | 3 of 3, exact | [0x54f4…963f](https://explorer-studio.genlayer.com/tx/0x54f418b533127986735147e62edab0b426dc4e71e6b5093afda91302397b963f) |
| 4 | Fernhollow Pool · rig-ghost (page says the worker is not found) | NOT_LISTED | none | 0.00% | 3 of 3, exact | [0xfee4…1894](https://explorer-studio.genlayer.com/tx/0xfee4b6a27d07cc4f5a6dedf1a00963913047213b6061b55dcd17239d82a01894) |
| 5 | Quillmoor Pool · rig-dark, read while its service was up | READ | 9.96, 10.09, 9.96, 10.00, 9.96 | 99.76% | 3 of 3, exact | [0x6f20…28d5](https://explorer-studio.genlayer.com/tx/0x6f209725a7c4fdb3511e5d6ce040967f92d8ab7f7a1794fca119cc99ec2828d5) |
| 6 | Quillmoor Pool · rig-dark, read inside its down period (6 to 9 minutes past every ten) | NO_READING · N1_PAGE_DARK | none |  | 3 of 3, exact | [0xc501…0bd5](https://explorer-studio.genlayer.com/tx/0xc501a3a16ccff3ee29249927398eb02d9ebde119ca108d912ca31a0e35fe0bd5) |

Reading 3 shows why a missing slot counts as zero. Averaging only the listed minutes would report 9.99 GH/s and pay in full for two minutes that never ran.

**One window, one answer (on chain).** Reading 1 became its window's official reading. A second `read` of the same window afterwards was refused by the contract ([0x42a2…96ac](https://explorer-studio.genlayer.com/tx/0x42a209a8d2951ec40e048ca5e3ed06c3a11edd0a442ce02427314c9bf29196ac): "this window already has its official reading #1"), so nobody can re-read a window later, after the page has changed, and pick a different result.

**Another contract relying on a reading (on chain).** [`MeterConsumerExample`](examples/consumer/meter_consumer_example.py) was deployed at [`0x035d9b2a531f84d3DB2235b634907c131d0d30fc`](https://explorer-studio.genlayer.com/address/0x035d9b2a531f84d3DB2235b634907c131d0d30fc), pointing at this MeterReader. `create_job` pinned meter 1 (rig-sixty), a five-minute window that had **not started yet** and a 10 GH/s target ([0x2314…29ca](https://explorer-studio.genlayer.com/tx/0x231482cc7893e11b7edbdb52e4871bdfd4ca33e0695f495d29aa0ad6c39029ca)). After the window, the window was read (reading 7, [0x9183…54a0](https://explorer-studio.genlayer.com/tx/0x9183f037786413c374f056996c51f25be670b21cc7163ba6f004e740b1c954a0)), and `settle_job` ([0x65cf…426b](https://explorer-studio.genlayer.com/tx/0x65cf1720e7655bf3acc913b8e722165c32dc277c31d9415ff16d9d2e14f9426b)) took the share from the window's official reading through `gl.get_contract_at(reader).view().window_share_bp(...)` and stored 60.14% (S1_CAPPED_PRO_RATA). It read no web page, called no model and never let the caller choose a reading.

Meters 1 to 5 were registered from [`examples/`](examples/). **Also on Testnet Bradbury Phase 2:** v3 at [`0x286A…29B4`](https://scan.bradbury.genlayer.com/address/0x286A160029D89b2C9fA6e1cEe0f31A954Eb329B4), with every live case repeated there: all six readings agreed exactly by a majority of Bradbury's validators (five of five, or three of four in a repeated round), a second read of a window refused, and the consumer pinning a window in advance and settling at 60.34% from its official reading; see [`../bradbury/README.md`](../bradbury/README.md#meterreader-on-bradbury).

Deployment: [`deployment.json`](deployment.json). Earlier versions are superseded and not used: three interim v3 deployments on 16 Nov while independent reviews were addressed (`0xB7C177b4E59Ee61ad1Bea52B523D899b4E2Eea39`, `0xAaB449D9adaD1286f71cDf6f91d9A4c1baFe9755`, `0x01a7E80e79f8870619c5982AFcDBf6444dDa223b`), v2 (`0x29762f9bce4F51e01696a947D24158c9C66B6636`, 1% per-slot tolerance, rejected for the reason above) and v1 (`0xF85Bc3858068958C8682b2fbB5f668FBc867776a`, no publishing lag and no window index).

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

- `get_meter(meter_id)`, `get_reading(reading_id)`, `get_readings(meter_id, limit)`, `get_latest_readings(limit)`, `get_window_readings(meter_id, window_start, slots)`, `get_window_reading(meter_id, window_start, slots)`;
- `window_share_bp(meter_id, window_start, slots, target_per_slot)` and `delivery_share_bp(reading_id, target_per_slot)`;
- `get_counts()` and `get_rules()` (every constant a reading is held to).

From another Intelligent Contract:

```python
reader = gl.get_contract_at(Address(METER_READER)).view()
# meter_id, window_start, slots and target were agreed (pinned) before the window
share = reader.window_share_bp(meter_id, window_start, slots, str(target_per_slot))["share_bp"]   # 0..10000
```

This is the pattern [`MeterConsumerExample`](examples/consumer/meter_consumer_example.py) runs live (above): pin the meter, the window and the target first, then pay by the official reading's share. Do not accept a reading id from whoever calls you. Pin a meter you have checked (`get_meter`: page, series, column, resolution), because anyone can register another meter for the same page.

To adapt it to a new kind of page, register a meter. The contract itself does not change: `source_name`, `series_name` and `value_label` tell the model what to copy, and the unit family tells the code how to read it.

## Tests

```bash
cd meter-reader
PYTHONPATH=. ../venv/bin/pytest tests/direct -q        # 186 direct-mode tests, web and model mocked
PYTHONPATH=. ../venv/bin/python tools/mutate.py        # 73 of 73 mutants caught
../venv/bin/genvm-lint check contracts/meter_reader.py
MR_KEY=<throwaway key> ../venv/bin/python tools/live_cases.py --deploy   # redo the live table on Studio
```

`tools/mutate.py` breaks the contract on purpose, one change at a time (73 changes: limits, resolution, the official-reading rule and read period, exact number conversion, timing, interpretation, units, leader checks, agreement, consumer figures, URL filter, prompt guards; among them a 1% per-slot tolerance put back, which the tests now catch), and confirms the tests catch every one.

The tests cover:
- registration rules, including 17 URL-filter cases;
- every outcome kind and reason;
- unit normalisation and count meters;
- 5-minute slots and timing;
- injection, through a page that tries to close the data block and through model answers that add fields or rows;
- views and caps, the publishing lag and the window index;
- validator agreement and rejection: the same value in another unit, a value one base unit or 1% off, resolution rounding and its edge, leader values off the resolution grid, a different slot set, a different kind or reason, a leader error, and 15 malformed leader results;
- one official reading per window: a later read refused after a `READ` or `NOT_LISTED`, retries allowed after a `NO_READING`, other windows separate; reading refused after the read period; a target off the resolution grid refused;
- exact number conversion (0.009 EH/s, 8.014 PH/s, exponents, a decimal comma after a dot refused);
- the shape guard on its own (19 malformed results), which is also applied to the agreed result before it is stored.

## Limits

- A reading is what one public page showed for one finished window. If the site itself reports wrong numbers, the reading is wrong in the same way. MeterReader removes the copying party from the trust chain, not the site.
- Pages that need a login, a click or more than about four seconds of script time cannot be read.
- Rows must carry UTC times on the slot grid. Pages in local time give `N2_FORMAT` by design.
- If validators read a page while it is posting a slot (a meter registered without enough publishing lag), their slot sets differ and no reading is agreed: nothing is stored, and the window can be read again within its read period. If instead every validator reads before the page posts the last slot, they agree, and that slot is stored as missing in the official reading. Register meters with enough publishing lag for the page.
- A window has no reading at all if its read period closes without a conclusive one (the page was dark or ambiguous throughout). Consumers need a default for that case, as [`MeterConsumerExample`](examples/consumer/meter_consumer_example.py) shows with `expire_job`. The example waits 30 minutes after the read period before it allows expiry, so that a read sent just before the close has been decided; a read still undecided after that (long rotations or an appeal) could become official after the job expired. A consumer that moves money should choose a margin to suit the network.
- Studio validators run different models. If a page's layout is ambiguous, validators may disagree, and the transaction then rotates to a new leader or ends undetermined. No wrong number is stored in that case.

## Versions

- Contract runner `py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6` (the header of the contract file).
- Test tooling pinned to exact commits in [`../requirements.txt`](../requirements.txt): genlayer-test 0.29.2, genvm-linter 0.11.1-rc.2, genlayer-py 0.18.0.
