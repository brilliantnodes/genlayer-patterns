# genlayer-patterns

Reusable GenLayer Intelligent Contracts built on one idea: **validators copy facts from public pages into fixed forms, and plain code decides.** The model never chooses an outcome, and validators compare what decided it, not prose.

| Contract | What it does | Studio address |
|---|---|---|
| [MeterReader](meter-reader/) | Turns one finished window of a public per-interval statistics table (hashrate per minute, messages per minute, ...) into an on-chain reading: every slot stored (missing slots kept as missing), validators agree slot by slot within a stated tolerance, plus a capped delivery share and a per-window index for consumers. A consumer contract reads it on chain. | [`0x2976…6636`](https://explorer-studio.genlayer.com/address/0x29762f9bce4F51e01696a947D24158c9C66B6636) |
| [RuleCheck](rule-check/) | Declarative fact rules over 1 to 3 public pages: anyone stores a template (facts with closed answer lists, plus an ordered rule table), validators settle the facts, code applies the first matching rule, and validators must agree on the facts that rule uses. A consumer contract acts on its verdicts on chain. | [`0x28BE…f21e`](https://explorer-studio.genlayer.com/address/0x28BEC7C9A99cd19c101fbaB1CaFe0b6e4Db3f21e) |

Consumer examples, each deployed and called live (another contract relying on a result without reading any page or calling any model):

| Consumer | Relies on | What it shows | Studio address |
|---|---|---|---|
| [MeterConsumerExample](meter-reader/examples/consumer/meter_consumer_example.py) | MeterReader | reads a reading and its capped share through `gl.get_contract_at(...).view()` and stores it (60.22%) | [`0xdda6…29a6`](https://explorer-studio.genlayer.com/address/0xdda671dF730E0fd3faFE4ED56b51B7a7Fa5529a6) |
| [ListingGateExample](rule-check/examples/consumer/listing_gate_example.py) | RuleCheck | admits, refuses or asks for a recheck by verdict; pins the one template it trusts, requires a recent check and the expected subject, uses each check once; refused another template's check, a stale check and a reused check on chain | [`0xA10A…00c4`](https://explorer-studio.genlayer.com/address/0xA10A7359fCFAe7643282994f02012b0e6C2500c4) |

Each folder has the contract, direct-mode tests, a command-line client, example inputs, the deployment record and a README covering the problem, the state design, why its equivalence check is shaped the way it is, failure modes, and live results with transaction links.

## What is new compared with the projects they came from

The ideas were first used inside two Brilliant Nodes projects on GenLayer, [RigSettle](https://github.com/brilliantnodes/rigsettle) (hashrate rental escrow) and [Launch Claim Checker](https://github.com/brilliantnodes/launch-claim-checker). In both projects the reading and deciding are welded to one use case. The contracts here are separate, general primitives with their own code, tests and deployments:

| | Inside the project | Here |
|---|---|---|
| **Reading a stats page** | RigSettle reads one kind of page (a pool's accepted hashrate in GH/s) as part of settling a rental, and validators agree on the **delivered share** within 2 points. | **MeterReader** reads any per-interval table described by a frozen meter (source name, series, column, unit family, slot length, tolerance, publishing lag). Validators agree **slot by slot**: the exact set of listed slots and every value within the meter's tolerance, so a leader cannot move value between slots. Every slot is stored; readings are indexed per window so several consumers can apply the same rule; any contract can read them. |
| **Checking facts against a rule** | Launch Claim Checker has a fixed set of claim types (four named ones and a free-text "other claim"), a fixed form and a rule table written in its code. | **RuleCheck** takes the facts and the rule table as **data**: anyone stores a template (1 to 3 pages, up to 8 facts with closed answers, up to 16 rules) and runs it on any pages. Consensus is **rule-scoped**: validators must reach the same verdict by the same rule with the same answers to the facts that rule uses, so a fact that decided nothing cannot stall agreement. |
| **Using the result** | Each project uses its own result internally. | Both results are made for other contracts: the two consumer examples above run live on Studio. |

All examples use fictional pools, coins and services. Test GEN on GenLayer Studio only.

## Run the tests

```bash
python3 -m venv venv && venv/bin/pip install -r requirements.txt
(cd meter-reader && PYTHONPATH=. ../venv/bin/pytest tests/direct -q)   # 145 tests
(cd rule-check   && PYTHONPATH=. ../venv/bin/pytest tests/direct -q)   # 132 tests (104 RuleCheck, 28 consumer gate)
(cd meter-reader && PYTHONPATH=. ../venv/bin/python tools/mutate.py)   # 53 of 53 mutants caught
(cd rule-check   && PYTHONPATH=. ../venv/bin/python tools/mutate.py)   # 45 of 45 mutants caught
(cd rule-check   && PYTHONPATH=. ../venv/bin/python tools/mutate_gate.py)   # 20 of 20 consumer-gate mutants caught
venv/bin/genvm-lint check meter-reader/contracts/meter_reader.py
venv/bin/genvm-lint check rule-check/contracts/rule_check.py
venv/bin/genvm-lint check rule-check/examples/consumer/listing_gate_example.py
```

## License

MIT, see [LICENSE](LICENSE). Built by Brilliant Nodes.
