# RuleCheck

A reusable GenLayer Intelligent Contract for checks of the form "a few facts on one to three public pages, plus a rule everyone agreed on beforehand". Anyone writes the check once, as data: the facts to look for, each with a closed list of answers, and an ordered rule table. Anyone can then run it on concrete pages. Validators settle the facts, and plain Python applies the rules.

**Live on GenLayer Studio:** [`0x28BEC7C9A99cd19c101fbaB1CaFe0b6e4Db3f21e`](https://explorer-studio.genlayer.com/address/0x28BEC7C9A99cd19c101fbaB1CaFe0b6e4Db3f21e) · contract source: [`contracts/rule_check.py`](contracts/rule_check.py) · MIT

## The problem

Many disputes come down to "what does this page say about X, and what follows from that". Examples:

- a coin claims "no premine", but its explorer shows block 1;
- a pool says mining was down, and its status page has the incident;
- a seller says the item shipped, and the carrier page shows the scan.

The rule is usually simple and agreed in advance. The facts sit on public pages. Asking a model "is the claim true?" mixes the two: the verdict then depends on how each model weighs things, and validators cannot agree on prose.

RuleCheck separates them:

- **A template is data, frozen on chain.** It holds the page labels, the facts (each a question plus a closed list of answers, with `unclear` always added) and the rules (conditions on facts, then a verdict), checked in order, with a default verdict when none applies.
- **The model only picks answers.** Each validator renders the pages, and its model picks one listed answer per fact. It is never asked for a verdict.
- **Code applies the rules.** The first rule whose conditions all hold gives the verdict and the rule id.
- **Validators agree on what decided it.** They need the same verdict, by the same rule, with the same answers to the facts *that rule uses*.

## How it works

`create_template(name, pages, facts, rules, default_verdict)`. The `pages`, `facts` and `rules` arguments are JSON text:

```json
pages: ["announcement", "explorer"]
facts: [
  {"key": "claims_no_premine", "question": "Does the announcement state that the coin has no premine?", "options": ["yes", "no"], "page": "announcement"},
  {"key": "early_allocation",  "question": "Does the explorer page show coins paid in the genesis block or block 1 to founders, developers, a treasury or insiders, beyond the ordinary mining reward?", "options": ["yes", "no"], "page": "explorer"},
  {"key": "block1_shown",      "question": "Does the explorer page show the outputs of block 1?", "options": ["yes", "no"], "page": "explorer"}
]
rules: [
  {"id": "R0_NOT_CLAIMED",      "when": {"claims_no_premine": "no"}, "verdict": "not_claimed"},
  {"id": "R1_EARLY_ALLOCATION", "when": {"early_allocation": "yes"}, "verdict": "contradicted"},
  {"id": "R2_CLEAN_BLOCK1",     "when": {"block1_shown": "yes", "early_allocation": "no"}, "verdict": "supported"}
]
default_verdict: "undetermined"
```

**Limits:**
- 1 to 3 pages;
- 1 to 8 facts, each with 2 to 6 answers (`unclear` is added automatically);
- 1 to 16 rules, each with 1 to 8 conditions;
- a condition may allow a list of answers (`{"status": ["mining", "unclear"]}`).

Keys, answers and verdicts are lowercase slugs, and rule ids are uppercase slugs. The template is validated in full before it is stored: unknown facts, impossible answers, duplicate ids and the reserved rule id `DEFAULT` are all refused. A stored template never changes.

`check(template_id, urls, subject)` takes one URL per page label, as a JSON list, plus an optional subject (stored, and shown to the model as data). The stored check holds:
- the verdict and the rule id;
- the rule's conditions;
- the **deciding facts** (the answers to the facts that rule uses) and all answers;
- which pages could be read;
- up to three short notes from the model, stored but never compared.

### Two deterministic guards on the answers

- **An answer that is not one of the fact's options becomes `unclear`**, so a malformed or injected answer can only lead to the default verdict or a rule that explicitly accepts `unclear`.
- **A fact tied to a page that could not be read is forced to `unclear`**, whatever the model said. A model cannot invent what an empty explorer page "shows".

If no page can be read at all, validators agree on that in one round and nothing is stored (the call reverts with "none of the pages could be read").

## Why this equivalence check

The validator function:

1. **Rebuilds the leader's result** (`_rebuild`):
   - `pages_read` must have one boolean per page;
   - the answers must cover exactly the template's facts, each answer must be one of that fact's options, and there must be no answer other than `unclear` for a page that was not read;
   - the notes must stay within the limits;
   - the leader's own answers, run through the rule table, must give the leader's verdict and rule.

   A leader that claims "supported" with answers that do not lead there is rejected.
2. **Runs the check itself** and compares (`_same_outcome`): the same verdict, the same rule id, and **the same answers to every fact the deciding rule uses**.

**Why rule-scoped:** the verdict depends only on the facts the matched rule reads, plus the fact that no earlier rule matched. Requiring agreement on every fact would stall consensus over facts that changed nothing, for example whether the announcement claims "no premine" when block 1 already shows a founders' allocation. Requiring only the same verdict would accept a leader that reached it for a different reason. Comparing the deciding rule's facts gives a stored record whose "why" is confirmed by every agreeing validator: the `deciding_facts` field.

**Worst case:** answers to facts that the deciding rule does not use are the leader's alone. They are stored under `answers` for information, but nothing was decided by them, and `deciding_facts` shows which answers were confirmed. The same holds for the notes and the per-page `read` flags: both are the leader's report. For a page that a deciding fact is tied to, the flag is confirmed indirectly, because an unread page forces that fact to `unclear` and the agreed answer would differ.

## State design

- `templates: TreeMap[str, Template]`: each template, frozen as sorted JSON (with `unclear` added), with its owner and creation time. There is no update method; a change means a new template.
- `checks: TreeMap[str, Check]`: the template id, URLs, subject, requester, time and the rebuilt result (verdict, rule, answers, notes, pages read). The rule's conditions and the deciding facts are derived on read from the stored template, so they cannot drift.
- `by_template: TreeMap[str, str]`: the latest 200 check ids per template, for `get_checks`. Older checks stay readable by id.

## Guards

- **Prompt injection.** Each page sits between its own `=====LABEL PAGE BEGIN/END=====` markers, labelled untrusted data. Any `=====` in page text is removed, so a page cannot forge a marker. Each page is cut to 6,000 characters. Only `facts` and `notes` are read from the model's answer: a "verdict" or "rule" in the answer is ignored.
- **URL filter.** The same filter as MeterReader: only public names and dotted public IPv4 addresses. User info, backslashes, IPv6 literals, single labels, numeric IP tricks, private, reserved and link-local ranges, and internal suffixes are refused.
- **Bounded input.** Template JSON is limited to 8,000 characters per argument, and the subject to 200 characters.

## Live results on Studio (14 Nov 2026)

The examples use fictional pages only: Examplecoin and Controlcoin are test coins whose pages are hosted with the Launch Claim Checker site, and Saltmarsh Pool is a fictional pool from the RigSettle demo. Templates: [`examples/template-launch-no-premine.json`](examples/template-launch-no-premine.json) (template 1, [store tx](https://explorer-studio.genlayer.com/tx/0x9398ac9caea9ac90d4514eb14554dad93319207be98c43320c3ffecb84cfa788)) and [`examples/template-pool-status.json`](examples/template-pool-status.json) (template 2, [store tx](https://explorer-studio.genlayer.com/tx/0x753446ca8f711e6046c3e35833763e52fd0d145130c695288ea868f34263de01)).

| Check | Template | Pages (fictional) | Verdict | Rule | Deciding facts | Validators | Transaction |
|---|---|---|---|---|---|---|---|
| 1 | 1 | Examplecoin announcement + explorer block 1 (2,000,000 EXM to a founders' address) | contradicted | R1_EARLY_ALLOCATION | early_allocation = yes | 3 agree | [0x5b64…fa09](https://explorer-studio.genlayer.com/tx/0x5b6453b5165087f900ecf00dc6d66686b91a5c596ff190fa8dcb76dc3082fa09) |
| 2 | 1 | Controlcoin announcement + explorer, first five blocks (miner reward only) | supported | R2_CLEAN_BLOCK1 | block1_shown = yes, early_allocation = no | 3 agree | [0xd134…f648](https://explorer-studio.genlayer.com/tx/0xd1347c21d79cef4771b06fbd01cd9918f62fad4085c531e7e4d29d3a2fe6f648) |
| 3 | 1 | Controlcoin announcement + an explorer URL that does not exist | undetermined | DEFAULT | none (explorer facts forced to unclear; explorer page not read) | 3 agree | [0x4a79…8354](https://explorer-studio.genlayer.com/tx/0x4a797a09ce0fa6ae70243c593325c3e12a101d0c3dc31dc886b597fe231c8354) |
| 4 | 2 | Saltmarsh Pool status page | mining_outage_reported | R1_MINING_AFFECTED | mining_incident = yes | 3 agree | [0x3734…2d15](https://explorer-studio.genlayer.com/tx/0x3734c848a0bb93919f15acb7c470e76d77f2e994f78d13fa6fe30bb1444b2d15) |

Check 4's status page also lists a website-only incident, so `website_only_incident` was `yes`. That answer did not decide anything, so validators did not need to agree on it.

Deployment: [`deployment.json`](deployment.json). Check inputs: [`examples/`](examples/).

## Use it

```bash
python3 -m venv venv && venv/bin/pip install -r ../requirements.txt
venv/bin/python tools/rc.py template examples/template-launch-no-premine.json   # prints the template id
venv/bin/python tools/rc.py check 1 examples/check-controlcoin.json
venv/bin/python tools/rc.py show <check_id>
```

Views: `get_template`, `get_check`, `get_checks(template_id, limit)`, `get_latest_checks(limit)`, `get_counts`, and `get_rules` (every limit, and the agreement rule in words).

Writing a good template:
- Ask about **observable facts** ("does the page show block 1?"), not conclusions ("is the claim true?").
- Tie each fact to the page it must come from with `page`, so an unreadable page cannot be filled in.
- Put the most decisive rule first, and keep `undetermined` (or a similar word) as the default.
- Use `unclear` in a condition only when "the page does not say" should itself decide.

## Trust model for users of a check

- **Read the template before relying on its verdicts.** A template's questions are written by its author and go into the prompt. A misleading question gives misleading answers, so judge a template by its questions and rules (`get_template`). Templates are public and never change.
- **Look at the URLs.** Whoever runs a check chooses the pages. A check record shows each page's label and URL, so a consumer should accept a verdict only for pages it expects (for example, an explorer on the project's own domain).
- **A check is a snapshot.** If a page changes, a new check can give a new verdict. Every check is kept with its time.

## Tests

```bash
cd rule-check
PYTHONPATH=. ../venv/bin/pytest tests/direct -q        # 104 direct-mode tests, web and model mocked
PYTHONPATH=. ../venv/bin/python tools/mutate.py        # 45 of 45 mutants caught
../venv/bin/genvm-lint check contracts/rule_check.py
```

`tools/mutate.py` breaks the contract on purpose, one change at a time (45 changes: rule order, answer guards, leader checks, agreement, template validation, URL filter, prompt), and confirms the tests catch every one. One change is left out because it cannot change behaviour: comparing the rule id but not the verdict, since each rule id fixes its verdict.

The tests cover:
- 37 template validation cases;
- first-match order and the default;
- invalid or injected answers, which become `unclear` and can never support;
- the unread-page guard and the all-pages-unreadable case;
- 12 URL-list and URL-filter cases;
- prompt content and marker forging;
- views and caps;
- validator agreement: unused facts ignored, the same verdict by another rule rejected (including an earlier rule firing while the deciding fact agrees), a different answer to a used fact rejected, unreadable agreeing only with unreadable, a leader error, and 19 malformed or lying leader results;
- the rebuild guard on its own, which is also applied to the agreed result before anything is stored.

## Limits

- A verdict describes what the supplied pages showed when they were read. It is not a proof about anything outside them, and a page can change after the check.
- The quality of a check is the quality of its questions. A vague question gives `unclear` or disagreement, never a confident wrong verdict by a rule that requires a clear answer. A template whose rules accept `unclear` decides on silence, by its author's choice.
- Pages that need a login, a click or more than about four seconds of script time cannot be read. Each page is cut to 6,000 characters, so a fact far down a long page may be missed (and then answered `unclear`).

## Versions

- Contract runner `py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6`.
- Test tooling pinned in [`../requirements.txt`](../requirements.txt): genlayer-test 0.29.2, genvm-linter 0.11.1-rc.2, genlayer-py 0.18.0.
