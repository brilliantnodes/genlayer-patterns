# genlayer-patterns

Reusable GenLayer Intelligent Contracts built on one idea: **validators copy facts from public pages into fixed forms, and plain code decides.** The model never chooses an outcome, and validators compare what decided it, not prose.

| Contract | What it does | Studio address |
|---|---|---|
| [MeterReader](meter-reader/) | Turns one finished window of a public per-interval statistics table (hashrate per minute, messages per minute, ...) into an on-chain reading: every slot stored (missing slots kept as missing), validators agree on every value exactly (after rounding down to the meter's resolution), and each window has one official reading, taken in a short read period after the window, so every consumer that agreed a meter, window and target gets the same share. A consumer contract pins a meter, window and target and pays by it on chain. | [`0xa0FE…209C`](https://explorer-studio.genlayer.com/address/0xa0FE27774c2f1F0d35bd83dA806cFB1F85F4209C) |
| [RuleCheck](rule-check/) | Declarative fact rules over 1 to 3 public pages: anyone stores a template (facts with closed answer lists, plus an ordered rule table), validators settle the facts, code applies the first matching rule, and validators must agree on the facts that rule uses. A consumer contract acts on its verdicts on chain. | [`0x28BE…f21e`](https://explorer-studio.genlayer.com/address/0x28BEC7C9A99cd19c101fbaB1CaFe0b6e4Db3f21e) |

Consumer examples, each deployed and called live (another contract relying on a result without reading any page or calling any model):

| Consumer | Relies on | What it shows | Studio address |
|---|---|---|---|
| [MeterConsumerExample](meter-reader/examples/consumer/meter_consumer_example.py) | MeterReader | pins a meter, a window that has not started yet and a target, then stores the share from the window's official reading through `gl.get_contract_at(...).view()` (60.14%); never takes a reading id from the caller; expires a job whose read period passes with no reading | [`0x035d…30fc`](https://explorer-studio.genlayer.com/address/0x035d9b2a531f84d3DB2235b634907c131d0d30fc) |
| [ListingGateExample](rule-check/examples/consumer/listing_gate_example.py) | RuleCheck | admits, refuses or asks for a recheck by verdict; pins the one template it trusts, requires a recent check and the expected subject, uses each check once; refused another template's check, a stale check and a reused check on chain | [`0xA10A…00c4`](https://explorer-studio.genlayer.com/address/0xA10A7359fCFAe7643282994f02012b0e6C2500c4) |

Each folder has the contract, direct-mode tests, a command-line client, example inputs, the deployment record and a README covering the problem, the state design, why its equivalence check is shaped the way it is, failure modes, and live results with transaction links.

## What is new compared with the projects they came from

The ideas were first used inside two Brilliant Nodes projects on GenLayer, [RigSettle](https://github.com/brilliantnodes/rigsettle) (hashrate rental escrow) and [Launch Claim Checker](https://github.com/brilliantnodes/launch-claim-checker). In both projects the reading and deciding are welded to one use case. The contracts here are separate, general primitives with their own code, tests and deployments:

| | Inside the project | Here |
|---|---|---|
| **Reading a stats page** | RigSettle reads one kind of page (a pool's accepted hashrate in GH/s) as part of settling a rental, and validators agree **exactly on the rule and share that decide the payout**. | **MeterReader** reads any per-interval table described by a frozen meter (source name, series, column, unit family, slot length, resolution, publishing lag). Validators agree **slot by slot, exactly**: the same listed slots and the same value in every slot, so a leader cannot move any value. Every slot is stored, and each window has one official reading, so every consumer that agreed the same meter, window and target gets the same share. |
| **Checking facts against a rule** | Launch Claim Checker has a fixed set of claim types (four named ones and a free-text "other claim"), a fixed form and a rule table written in its code. | **RuleCheck** takes the facts and the rule table as **data**: anyone stores a template (1 to 3 pages, up to 8 facts with closed answers, up to 16 rules) and runs it on any pages. Consensus is **rule-scoped**: validators must reach the same verdict by the same rule with the same answers to the facts that rule uses, so a fact that decided nothing cannot stall agreement. |
| **Using the result** | Each project uses its own result internally. | Both results are made for other contracts: the two consumer examples above run live on Studio. |

## Also on Testnet Bradbury Phase 2

All four contracts also run on **Bradbury Phase 2** (chain 4221, validators with real models and web access), from builds made by [`bradbury/port.py`](bradbury/port.py) for GenVM v0.6. The same tests pass on v0.6, and every live case was repeated there (5 validators per round). Details and transaction links: [`bradbury/README.md`](bradbury/README.md).

| Contract | Bradbury address |
|---|---|
| MeterReader (v3) | [`0x286A…29B4`](https://scan.bradbury.genlayer.com/address/0x286A160029D89b2C9fA6e1cEe0f31A954Eb329B4) |
| MeterConsumerExample (v3) | [`0xF614…B0d0`](https://scan.bradbury.genlayer.com/address/0xF6140a94a74fFf9937AB660031E14370944AB0d0) |
| RuleCheck | [`0x7525…96b4`](https://scan.bradbury.genlayer.com/address/0x7525aC6d34dd2189E290C4396d9b78f7eD1196b4) |
| ListingGateExample | [`0x013a…c873`](https://scan.bradbury.genlayer.com/address/0x013ac1916cB3C108fA8b443DCcbdFc8F9e5Cc873) |

All examples use fictional pools, coins and services. Test GEN only (Studio and Bradbury).

## Run the tests

```bash
python3 -m venv venv && venv/bin/pip install -r requirements.txt
(cd meter-reader && PYTHONPATH=. ../venv/bin/pytest tests/direct -q)   # 186 tests
(cd rule-check   && PYTHONPATH=. ../venv/bin/pytest tests/direct -q)   # 132 tests (104 RuleCheck, 28 consumer gate)
(cd meter-reader && PYTHONPATH=. ../venv/bin/python tools/mutate.py)   # 73 of 73 mutants caught
(cd rule-check   && PYTHONPATH=. ../venv/bin/python tools/mutate.py)   # 45 of 45 mutants caught
(cd rule-check   && PYTHONPATH=. ../venv/bin/python tools/mutate_gate.py)   # 20 of 20 consumer-gate mutants caught
venv/bin/genvm-lint check meter-reader/contracts/meter_reader.py
venv/bin/genvm-lint check rule-check/contracts/rule_check.py
venv/bin/genvm-lint check rule-check/examples/consumer/listing_gate_example.py
```

The same tests against the Bradbury (GenVM v0.6) builds: see [`bradbury/README.md`](bradbury/README.md#why-a-separate-build).

## License

MIT, see [LICENSE](LICENSE). Built by Brilliant Nodes.
