# genlayer-patterns

Reusable GenLayer Intelligent Contracts built on one idea: **validators copy facts from public pages into fixed forms, and plain code decides.** The model never chooses an outcome, and validators compare what decided it, not prose.

| Contract | What it does | Studio address |
|---|---|---|
| [MeterReader](meter-reader/) | Turns one finished window of a public per-interval statistics table (hashrate per minute, messages per minute, ...) into an on-chain reading: every slot stored (missing slots kept as missing), validators agree slot by slot within a stated tolerance, plus a capped delivery share for consumers. | [`0xF85B…776a`](https://explorer-studio.genlayer.com/address/0xF85Bc3858068958C8682b2fbB5f668FBc867776a) |
| [RuleCheck](rule-check/) | Declarative fact rules over 1 to 3 public pages: anyone stores a template (facts with closed answer lists, plus an ordered rule table), validators settle the facts, code applies the first matching rule, and validators must agree on the facts that rule uses. | [`0x28BE…f21e`](https://explorer-studio.genlayer.com/address/0x28BEC7C9A99cd19c101fbaB1CaFe0b6e4Db3f21e) |

Each folder has the contract, direct-mode tests, a command-line client, example inputs, the deployment record and a README covering the problem, the state design, why its equivalence check is shaped the way it is, failure modes, and live results with transaction links.

Both contracts grew out of two Brilliant Nodes projects on GenLayer: [RigSettle](https://github.com/brilliantnodes/rigsettle) (hashrate rental escrow) and [Launch Claim Checker](https://github.com/brilliantnodes/launch-claim-checker). Here the reading and deciding parts stand on their own, so other contracts and apps can reuse them.

All examples use fictional pools, coins and services. Test GEN on GenLayer Studio only.

## Run the tests

```bash
python3 -m venv venv && venv/bin/pip install -r requirements.txt
(cd meter-reader && PYTHONPATH=. ../venv/bin/pytest tests/direct -q)   # 119 tests
(cd rule-check   && PYTHONPATH=. ../venv/bin/pytest tests/direct -q)   # 101 tests
venv/bin/genvm-lint check meter-reader/contracts/meter_reader.py
venv/bin/genvm-lint check rule-check/contracts/rule_check.py
```

## License

MIT, see [LICENSE](LICENSE). Built by Brilliant Nodes.
