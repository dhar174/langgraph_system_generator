# #334-B offline verification

Part of #334; related to #129. The study and the Luna request migration
were exercised offline. Live semantic reviewer quality remains unmeasured.

## Production migration checkpoint

The fetched base was `63576b4efc283e6e8404ec9cfaef6801b77b81e1`
(PR #401). The production migration and fixture generation baseline was
`0da1b02387a1bc15844aa2f7e24207382ec48995`. Tests at that revision used
Python 3.12.2 on Windows, a task-private environment with the project's GCP
extra, and the offline qualification guard. LangChain OpenAI 1.7.2, OpenAI
3.35.1, and nbconvert 7.16.6 were installed in that environment.

| Command at migration checkpoint | Exit | Observed result |
| --- | ---: | --- |
| `python -m pytest tests/unit -k "semantic or credential or endpoint or outcomes or luna" --asyncio-mode=auto -q` | 0 | 395 passed, 1,147 deselected |
| `python -m pytest tests/unit/ --asyncio-mode=auto -q` | 0 | 1,542 passed |
| `python -m pytest tests/patterns/ -v` | 0 | 82 passed |
| `python -m pytest --asyncio-mode=auto -ra` | 0 | 1,661 passed, 7 skipped |
| `python scripts/qualify_durable_backend.py --level sdk --test-timeout 900 --receipts output/qualification/migration-exact-sdk` | 0 | 244 passed, 0 skipped |
| `python scripts/run_generated_notebook_eval.py --qualify-outcomes --output output/migration-exact-381` | 0 | 3 fixtures, 110 assertions, 4 negative controls |
| `python -m pytest tests/unit/test_documentation_coverage.py -q` | 0 | 5 passed |
| `python -m flake8 src tests scripts --count --select=E9,F63,F7,F82 --show-source --statistics` | 0 | 0 findings |

The full suite skipped four Firestore emulator opt-ins and three packaging
install smoke opt-ins. The exact fetched base passed durable SDK
qualification (243 tests, no skips) and the same three #381 fixtures and
four negative controls. The #381 evaluator, its existing fixture source,
and the historical six-case semantic contract set retain their own scope.
The local stub export smoke produced a valid notebook, HTML, and a
four-member ZIP. Its generation outcome carried `not_run` execution
status. The export command exited 0.

```text
python -m langgraph_system_generator.cli generate "Create a router-based customer support chatbot with billing and technical routes." --mode stub --output ./output/334-b-stub-verified --formats ipynb html zip
```

Broad static diagnostics at the migration checkpoint were compared with
the exact fetched base. Both revisions returned exit 1 for each broad
command.

| Command | Base | Migration checkpoint | Added diagnostics |
| --- | ---: | ---: | ---: |
| `python -m ruff check src tests scripts examples --output-format=json` | 1,375 | 1,375 | 0 |
| `python -m black --check src tests scripts examples` | 89 files | 88 files | 0 |
| `python -m mypy src` | 104 | 101 | 0 |

## Study implementation checkpoint

The evaluation implementation and candidate snapshots were committed at
`4aae9bf3cf80046ba8e96efc0a55f3abe1b1ef16`. The focused semantic,
credential, endpoint, outcome, and Luna selection passed 420 tests
(1,147 deselected). Durable SDK qualification passed 244 tests with zero
skips. The subsequent reference-label review records the human decisions
still pending for a pilot.

The tracked study corpus has 20 cases. Sixteen are clean and defective
members of eight scenario families. The other four are reported as
guardrails. The two generator-derived pairs use full offline exports
with fake generation dependencies and explicit altered copies. Production
static QA reported zero blockers on the paired cases and did not detect the
eight intended mutations. Some generated candidates have nonblocking QA
warnings. The label review records their relevance to the paired
requirements and how to handle them during adjudication.

| Command at study implementation checkpoint | Exit | Observed result |
| --- | ---: | --- |
| `python -m pytest tests/unit -k "semantic or credential or endpoint or outcomes or luna" --asyncio-mode=auto -q` | 0 | 420 passed, 1,147 deselected |
| `python -m pytest tests/unit/ --asyncio-mode=auto -q` | 0 | 1,567 passed |
| `python -m pytest tests/patterns/ -v` | 0 | 82 passed |
| `python -m pytest --asyncio-mode=auto -ra` | 0 | 1,686 passed, 7 skipped |
| `python scripts/qualify_durable_backend.py --level sdk --test-timeout 900 --receipts output/qualification/final-gates-sdk` | 0 | 244 passed, 0 skipped |
| `python -m pytest tests/unit/test_documentation_coverage.py -q` | 0 | 5 passed |
| `python -m flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics` | 0 | 0 findings |

The full suite skipped the same four Firestore emulator and three packaging
install smoke opt-ins as the migration checkpoint.

The initial `python scripts/run_generated_notebook_eval.py --qualify-outcomes
--output output/final-gates-381` attempt exited 1. All 110 behavioral
assertions and four negative controls completed. The evaluator rejected
qualification because label and documentation files changed during the run.
The clean checkout rerun at `7dbb3ec67728c30a4a58606c475513ed35c08b16`
exited 0, qualified all three fixtures, and detected all four controls.
The rerun used `python scripts/run_generated_notebook_eval.py
--qualify-outcomes --output output/frozen-qualification-381`.

Broad static checks used the same commands and exact base as the first table.
Ruff exited 1 with 1,485 findings, including 110 added diagnostics in the
four generated notebook snapshots and altered copies. Those snapshots retain
their generated code and recorded bytes. The authored benchmark Python
files passed focused Ruff and Black. Broad Black exited 1 with 88 files and
no new formatting diagnostics. Broad mypy exited 1 with 101 errors and
no new diagnostics.

## Frozen labels and synthetic evidence

Revision `7dbb3ec67728c30a4a58606c475513ed35c08b16` incorporates
the independent label review. Its candidate and dataset bytes match the
study implementation checkpoint. In a clean checkout pinned to this
revision, the corpus, runner, and scoring tests passed 25 cases and
focused Ruff, Black, and mypy exited 0. The later receipt commit records
documentation only.

```text
python -m pytest tests/unit/test_semantic_quality_corpus.py tests/unit/test_semantic_quality_runner.py tests/unit/test_semantic_quality_scoring.py -q --tb=short
python scripts/evaluate_semantic_review.py plan --model gpt-6-luna --endpoint-policy local --output output/semantic-7dbb3ec/semantic-plan.json
python scripts/evaluate_semantic_review.py dry-run --plan output/semantic-7dbb3ec/semantic-plan.json --output output/semantic-7dbb3ec/semantic-dry-run.json
python scripts/evaluate_semantic_review.py score --receipt output/semantic-7dbb3ec/semantic-dry-run.json --plan output/semantic-7dbb3ec/semantic-plan.json --output output/semantic-7dbb3ec/semantic-score.json
```

Each command exited 0. The dry run recorded all 40 slots, 38 fake
transport requests, 36 completed reviews, two insufficient-context
abstentions, and two pre-dispatch input-limit outcomes. All 32 paired
trials returned valid reviews. Guardrail agreement was 8 of 8. Finding
precision is N/A pending independent adjudication. The synthetic findings
cannot support an accuracy or detection claim.

- [Proposed pilot plan](2026-11-13-334-b-pilot-plan.md)
- [Synthetic score report](2026-11-13-334-b-synthetic-score.md)
- [Independent reference-label review and human handoff](2026-11-13-334-b-label-review.md)

The sample plan uses the official OpenAI Responses endpoint for
`gpt-6-luna`, low reasoning, two repetitions per case, concurrency one,
a 30-second deadline, an effective output cap of 2,048 tokens, and zero
retries. The ceiling is 40 reviewer attempts, with at most 38 for this
selection after preflight. The pilot remains unexecuted. For a future
pilot, create and separately approve a plan from the checkout and
environment that will run it.
