# 381-A generated-notebook execution verification

Part of #381. This receipt qualifies the controlled fixture behaviors below;
it does not enable production notebook execution or change outcome version 1.

## Source and evidence

- Base: `1f674b4da8552d8a258fd44fc438436e4a1d61e5`.
- Windows full-run source: `21655e783fa401537ec5fbc2258cb9e3490b9f74`, clean working tree.
- Follow-up compatibility source: `f7db661fd61b192b6277ea85f6e7df5094cba530`.
  This adds an inspectable coroutine adapter around the same async fixture
  collaborators. The earlier Windows receipt is retained with its original
  source identity, not relabeled as evidence from this later commit.
- Windows full-run source tree SHA-256: `8d46aeada50524e6730e0ac7cf29dc11b0b63726cb29121cd69c3c3d00c72b3a`.
- PR: [#398](https://github.com/dhar174/langgraph_system_generator/pull/398).
- Final full-run evidence root (local, Git-ignored):
  `output/381-a-full-artifacts/test_generated_graphs_and_nega0/evaluation/`.
- Full log, exit receipt and JUnit: `output/381-a-full.log`,
  `output/381-a-full.exit`, `output/381-a-full-junit.xml`.

The root contains report.json, summary.md and per-case receipts, original
exported notebooks, generated_cells.json, manifests, derived source/executed
notebooks, mutation copies and bounded process logs. Development dev1/dev2
outputs were diagnostic attempts and are not final qualification evidence.

## Actual artifacts and behaviors

All three cases use `generate_artifacts(mode="live")` with deterministic
module-local fake model responses. The normal requirements, graph design,
tool planning, composition, static QA and export paths execute. Retrieval and
environment smoke are explicitly mocked. No paid provider is called.

| Case | Serialized cells | Original code cells completed | Derived code cells completed | Assertions |
| --- | ---: | ---: | ---: | ---: |
| support-router | 25 | 11 | 13 | 34 passed |
| supervisor | 24 | 10 | 12 | 25 passed |
| chatbot-tool | 24 | 10 | 12 | 51 passed |

The original dependency-installation cell is excluded and disclosed in each
receipt. Derived cells add external fixture bootstrap and behavioral probes.
Each original file exists, is valid nbformat v4, matches its byte hash and
`notebook-cells-v1` identity, matches serialized candidate/manifest evidence,
and remains unchanged after execution. Disabling nbclient timing metadata
preserves source identity when outputs and execution counts are added.

| Case | Original notebook byte SHA-256 | notebook-cells-v1 candidate SHA-256 |
| --- | --- | --- |
| support-router | `257f4d6c4f742ac3074da7ee5643cf45713ce99d820e259d7b75812ebac1f0bf` | `f64c5c532458f23a6381a3f2c06dbab32bcee837b01411833024cbd83320ffe2` |
| supervisor | `4e5d76e7e0832134999e138f7703b46e8b601e269887f878e2f10dcc11f8da7d` | `8686008c970c1309ed0ffc863f6226052aab205690ba19c37aba18cdbb56b139` |
| chatbot-tool | `9e881e7934447d0551db13a5d7b81cf56b9dcc32230fdcb75f89465980f3e5b4` | `61fe2d4a1f16ad12220cb90135c63d462efea2b1687880e3cc2b07b2349bcf7f` |

- Router: billing, technical and unsupported requests execute only the expected
  specialist/fallback branch; streamed state, result values and terminal
  checkpoints match expectations.
- Supervisor: researcher and reviewer receive the required task and produce
  distinct outputs; checkpoint tasks demonstrate the same-superstep fan-out;
  reducer state combines results and finish observes both. A selected worker
  raises ValueError and the invocation aborts with unfinished checkpoint tasks,
  matching the declared policy.
- Chatbot: the second same-thread turn receives retained context, another
  thread does not share it, and the calculator path executes real ToolNode
  dispatch with observed callback arguments `{a: 2, b: 3}`, ToolMessage `5`,
  and final response `Tool result: 5`. Ordinary requests emit no tool call.
  `RUN_INTERACTIVE_LOOP=False` is executed and asserted.

All three clean cases pass static QA as well as their separate behavioral
assertions. Their production manifests still report generated execution
`not_run`. Packaging, environment smoke, static QA and this separate behavioral
receipt remain distinct qualifications.

## Negative controls

All four mutation copies have changed candidate identities, preserve the
original artifacts and use the same execution environment as the clean case.
All seven clean/mutant executions report verified cleanup.

| Mutation | Observed failure | Required detection |
| --- | --- | --- |
| runtime-failure | CellExecutionError / kernel RuntimeError at original graph cell 20 | Classified actual executable-cell failure |
| wrong-route | `billing:executed_nodes` and route/result assertions fail | Wrong valid destination is detected |
| unreachable-tool | `tool-turn:actual_tool_executions`, tool callbacks/arguments/result assertions fail | Missing actual tool execution is detected |
| nontermination | CellTimeoutError at original execution cell 22 after 20 seconds | Actual generated graph node loop is bounded; cleanup verified |

No mutation was accepted merely because setup, imports or isolation failed.
There are no skipped harness cases or negative controls.

## Local validation

| Command/check | Actual result |
| --- | --- |
| `python -m pytest --asyncio-mode=auto --basetemp output/381-a-full-artifacts --junitxml output/381-a-full-junit.xml -ra` | Exit 0; **1,397 passed, 101 skipped, 5 warnings**, 687.63 seconds; JUnit 1,498 tests, 0 failures/errors |
| `python -m pytest tests/unit/ --asyncio-mode=auto -q` | Development run: exit 0; 1,271 passed, 94 skipped; final full run additionally includes the later harness unit checks |
| `python -m pytest tests/patterns/ -v` | Exit 0; 82 passed |
| Focused composer/outcome/evaluation regression set | Exit 0; 102 passed before the final additional harness unit checks |
| Latest harness unit subset | Exit 0; 18 passed, including real detached-process kill/reap, open-pipe cleanup rejection and real LangGraph invocation through the async fixture adapter |
| Python 3.10 adapter compatibility | Actual adapter extracted from its source AST: signature inspection and awaited AsyncMock result pass on CPython 3.10.19; this does not claim a full Python 3.10 graph run |
| Focused generated-notebook integration | Exit 0; 1 passed, exercising all three clean cases and all four controls |
| `python -m flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics` | Exit 0; 0 fatal errors |
| `node --check src/langgraph_system_generator/api/static/app.js` | Exit 0 |
| `git diff --check` | Exit 0 |
| Ruff on new/changed harness owners | Exit 0 |
| Mypy on the five new modules with `--follow-imports=silent` | Exit 0; no issues in 5 source files |
| Follow-up mypy on `qa/execution_fixtures.py` with `--follow-imports=silent` | Exit 0; no issues in 1 source file after the Python 3.10 adapter correction |

The 101 full-run skips are explicit optional-lane exclusions: 89 missing
Firestore SDK, 5 missing Cloud Tasks SDK, 4 emulator opt-ins, and 3 packaging
smoke opt-ins. They do not conceal any of the seven required harness executions.

Global static checks remain non-green because of inherited findings:

- `ruff check src/ tests/`: base and head both **1,238** findings, with no new
  normalized path/code/message diagnostics.
- `black --check src/ tests/`: base and head both identify the same **76**
  existing files needing formatting. New harness files are formatted; no
  unrelated reformat was applied.
- `mypy src/`: base reports **109 errors in 16 files**, head **107 in 16 files**;
  normalized comparison has no additions. The two absent diagnostics concern
  untyped Google SDK imports; this is not a claim those inherited types were fixed.

Environment: Windows CPython 3.12.2; langgraph 1.2.16, langchain 1.4.6,
langchain-core 1.6.12, langchain-openai 1.7.2, nbformat 5.10.4,
nbclient 0.10.4 and ipykernel 7.2.0. Some installed notebook/dev packages are
older than requirements.txt floors, so this is actual-environment evidence,
not a claim of dependency-floor parity.

## Hosted checks

At source `21655e7`, hosted Python build found two new failures.
The detached-process test assumed Popen retained an exit status after psutil
reaped it. A test-only correction checks prompt process death directly. The
integration assertion now exposes bounded receipt diagnostics rather than only
an ephemeral runner path. At `c55e684`, hosted build reports 1 failed, 1,337
passed and 140 skipped. Its diagnostics identify Python 3.10 signature
inspection of a bare AsyncMock during LangGraph node registration. The exact
TypeError was reproduced with Python 3.10.19; `f7db661` wraps those async mocks
in real coroutine functions without changing fixture results. The focused
18-test suite and Python 3.10 adapter check pass. Hosted follow-up run
[39876862187](https://github.com/dhar174/langgraph_system_generator/actions/runs/39876862187)
passed at exact source `f7db661fd61b192b6277ea85f6e7df5094cba530`:
**1,339 passed, 140 skipped, 1 warning in 126.23 seconds**, including the
generated-notebook integration and all 18 harness unit checks. This proves the
same three clean-case and four mutation gates passed on hosted Ubuntu/Python
3.10; its ephemeral notebook receipts were not downloaded or relabeled as the
Windows receipts above. The hosted skip set differs from the local installed
environment. CodeQL (actions, Python and JavaScript), docs coverage and both
credential-free durable qualification jobs also passed at that exact source.
Any later documentation-only commit has its own hosted check status; this
receipt does not imply those subsequent checks have completed.

## Independent review and limits

One production writer implemented the changes. Read-only evidence review and
isolation review have no remaining blocking findings for the trusted-fixture
scope at `21655e7`. Corrections include source-tree provenance, actual tool
argument callbacks, mutation-specific failure gates, async kernel timeout
handling, observed detached-descendant cleanup and withholding cleanup approval
until output pipes close. Bounded atomic receipt replacement retries address
transient Windows sharing violations.
The evidence reviewer also reviewed the narrow `f7db661` coroutine-adapter
change with no blockers and independently ran its 18 focused tests on Python
3.12.2; that review does not claim an independent Python 3.10 graph run.

Windows uses aggregate Job Object memory/user-CPU limits; POSIX applies
per-process inherited memory/CPU rlimits. Python TCP, UDP-sendto, DNS and gRPC
guards preserve kernel loopback, but native code and other APIs such as POSIX
sendmsg bypass them. The child has the user's filesystem privileges. An
unobserved POSIX descendant that escapes its session and closes inherited pipes
cannot be enumerated reliably. These are trusted fixtures, not a malicious-code
sandbox. Live models, arbitrary tools, cross-restart checkpoints, broader
architectures, production execution and deployment remain unverified.

Complexity increased to add separate case models, fixture responses, kernel
probes, execution and repository-runner owners. New maintained files remain
below 800 lines; the existing large NotebookComposer gains 37 net lines for
declared tool-chatbot behavior and canonical supervisor Send dispatch. No new
subprocess framework or production qualification adapter was introduced.

## B handoff and stop gates

381-B must verify receipt provenance and selected-candidate association before
extending the public generated-execution contract. It must not infer execution
from export, static checks or the environment-smoke notebook. Outcome version 1,
GeneratedExecutionOutcome's `not_run`, manifests, jobs and browser labels are
preserved here. This PR adds no automatic runtime QA gating or API/worker
arbitrary-notebook execution. Do not merge, deploy, provision infrastructure or
close #381 as part of this assignment.

## Review follow-up, 2026-10-23

Two PR #398 findings are addressed after the qualified revisions above:
deterministic chatbot tool nodes now record fallback provenance and a visible
banner, and canonical subagent fan-out is supplied through the registered
graph-section builder. Registered variants can reuse that builder with a
renamed coordinator; the generic renderer retains scalar routing by default.
Regression cases cover both tool-node kinds, renamed and legacy coordinators,
two-worker dispatch, scalar fallback, terminal selection and registry opt-in.

The user explicitly requested skipping local CI and pre-push checks for this
review follow-up. These added regression cases were not run locally, and no
earlier passing receipt qualifies the changed source or candidate identities.
The historical results above retain their original revision associations.
