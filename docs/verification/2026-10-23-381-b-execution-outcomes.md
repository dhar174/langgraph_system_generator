# #381-B execution outcome verification

## Authority and boundary

- Approved implementation plan: conversation, 2026-10-23; explicit evaluator only,
  receipt plus new local evaluated bundle, originals preserved.
- Base: `d599e602272261d38516d121ff02b61643c29c8b`.
- Accepted prerequisite: PR #398, head `20e0c4af297b2b1840a30487b85c6f653ddae8af`;
  current base tree is identical. PR #397 supplies outcome v1.
- No merge, deployment, cloud configuration, production execution or issue changes.

## Source and delivery

Implementation and final execution source:
`185b073f3e8825462a8445fd9db2b31ea010c5e4`.
The delivery follow-up updates documentation only; it must have no source, script
or test diff from this revision. Its published SHA and exact-head hosted check
state are recorded in [PR #399](https://github.com/dhar174/langgraph_system_generator/pull/399).
The PR remains open and unmerged. #380 remains open. #381 was already closed when
this work began; no issue state was changed.

## Commands and inspected results

Windows CPython 3.12.2, existing notebook/GCP SDK environment. `PYTHONPATH` points
to this worktree's `src`; dotenv/tracing are disabled and provider/cloud secrets
are removed from child command environments. Tests mock models and transports.
Raw command, PID, start/end, source SHA, stdout/stderr and exit receipts are retained
under ignored `output/verification381b/`; JUnit confirms zero failures/errors.

| Command or gate | Observed result |
| --- | --- |
| `python -m pytest tests/unit/ --asyncio-mode=auto -q --junitxml=output/verification381b/units.xml` | Exit 0; 1,438 passed, 0 skips, 5 warnings; began at `ec1ff43` before the last source-fact reader correction |
| Final focused admission/compatibility tests | Exit 0; 50 passed after the final reader correction |
| `python -m pytest tests/patterns/ -v --junitxml=output/verification381b/patterns.xml` | Exit 0; 82 passed at `185b073` |
| `python -m pytest --asyncio-mode=auto -ra --basetemp=output/verification381b/full-artifacts --junitxml=output/verification381b/full.xml` | Exit 0; 1,558 passed, 7 skipped, 5 warnings; 1,565 collected, zero failures/errors at `185b073` |
| `python scripts/qualify_durable_backend.py --level sdk --receipts output/verification381b/durable-sdk --test-timeout 900` | Exit 0; 243/243 passed, zero skips; real SDK imports, fake transports and credential-free guards |
| `python scripts/run_generated_notebook_eval.py --qualify-outcomes --output output/verification381b/evaluated-final` | Exit 0 at clean `185b073`; 3 cases, 110 assertions, all 4 negative controls detected, cleanup verified |
| `python -m langgraph_system_generator.cli generate "Build a support router" --mode stub --agent-type router --formats ipynb html zip --output output/verification381b/stub` | Exit 0; actual IPYNB/HTML/ZIP files; v1, static/execution not_run, usability unknown |
| Independent final artifact checker | Exit 0; byte/candidate/receipt/inventory checks, source metadata preservation, behavior observations and notebook/HTML/ZIP QA prose agree |
| Focused Ruff / Black | Exit 0; eight outcome/evaluation/test owners pass Ruff; nine owners including runner pass Black |
| Isolated mypy (`--follow-imports=skip`) | Exit 0; outcome models, derivation, qualification and bundle modules |
| Fatal Flake8 (`E9,F63,F7,F82`) over tracked Python files | Exit 0; zero fatal errors |
| `node --check src/langgraph_system_generator/api/static/app.js`; `git diff --check` | Exit 0 |

The final full suite includes the later reader correction and its added regression;
the earlier standalone unit run is not relabeled as final-source qualification.
The seven full-suite skips are four local Firestore-emulator opt-ins and three
isolated packaging-install opt-ins. These optional local lanes were not executed.

Broad static analysis intentionally retains inherited debt. Same tool environment,
archived exact base, duplicate-preserving identities normalized for line/path drift:
Ruff **14 -> 14**, mypy **104 -> 104**, Black **69 -> 69** files, with **zero added
identities/files**. Each broad command exits 1; these are not clean-tool claims.
Runner path bootstrap has existing E402 diagnostics; targeted runner checking
accounts for that existing bootstrap rule. No unrelated static cleanup is included.

## Exact executed candidates and dataset

Evaluator: `trusted-fixture-qualification-v1`; receipt schema 1, case versions 1.
Approved normalized dataset SHA-256:
`600eaf4fed1f76128e4db8feaecbcad7340b6b8c5a56c256763590d5523e2805`.
Evaluator/generator source-file map digest:
`7a4cefceaf47f390a8b600680dd19aff63318edb908dc54402fb30a569536d6a`.

| Case | notebook-cells-v1 candidate | Exact executed source notebook SHA-256 | Assertions |
| --- | --- | --- | --- |
| support-router | `f64c5c532458f23a6381a3f2c06dbab32bcee837b01411833024cbd83320ffe2` | `abdcdf72c21d489619e5543ebe6505b60c5e7f1faed72974984cd2a21993cdc4` | 34/34 passed |
| supervisor | `8686008c970c1309ed0ffc863f6226052aab205690ba19c37aba18cdbb56b139` | `be279905c9cf6fcd32eff3c6c4c5db69876b6b54a93ac129aa9f2eef14718ce2` | 25/25 passed |
| chatbot-tool | `8f5a3f796df0222e8eb03c2b6b7d1d6ddd595e28d7c4aa20fa9dbd96ab36f848` | `da07cf2ea41a91cc4936d6881d0edd0992bddbf724fbe8cf451da8314a5eb9af` | 51/51 passed |

Observed router destinations: billing, technical and fallback. Supervisor evidence
includes real Send fan-out, reducer aggregation, synthesis, and the declared worker
abort policy. Chatbot evidence includes same-thread retention, separate-thread
isolation, real ToolNode callbacks/arguments/result, and no-tool completion.
All three public execution results are passed; overall quality retains existing
static advisories rather than treating execution as full requirements verification.

Actual package versions: langgraph 1.2.16, langchain 1.4.6, langchain-core 1.6.12,
langchain-openai 1.7.2, nbformat 5.10.4, nbclient 0.10.4, ipykernel 7.2.0.
These are observed versions, not dependency-floor parity claims.

Windows Job Object bounds: aggregate 2,048 MiB committed memory and 90 CPU seconds;
20-second cell timeout, 180-second case timeout, 65,536-byte capture budget.
Temporary kernel working directories, allowlisted environment, synthetic fixture
credential, Python TCP/UDP/DNS/gRPC loopback guards, and verified descendant cleanup.
Native networking and the user's filesystem privileges are not contained.

## Negative controls and compatibility

All four mutations preserve originals and change the mutant candidate identity.
Runtime-breaking code produced `CellExecutionError`; wrong routing failed the
executed-node and route/state assertions; unreachable tool failed actual tool
execution/callback/argument/result assertions; nontermination produced a real
`CellTimeoutError`. Every control failed for its intended reason and verified cleanup.
Mutation receipts cannot qualify the original candidate.

Regressions cover stale/repaired/reordered/metadata-modified candidates, wrong
byte hashes/case/schema/configuration, missing/duplicate assertions, incomplete
cells, altered manifest/cells after kernel launch, manual typed/JSON claims, missing
dependencies, pre-graph errors, first-node failures before any yielded update,
isolation/cleanup failures, static/execution independence, v1/missing/future readers,
API request rejection, browser/SSE retrieval-only recovery and diagnostic downloads.
Durable tests verify rejection before object upload, unchanged job state, immutable
publication and no quality-induced generation retry.

The first execution attempt used an environment without ipykernel metadata and
failed before kernel launch. It exposed source-snapshot loss during dependency
preflight; corrected code retains identity and emits unavailable qualification,
without an executed-byte claim. Its failed receipt remains preserved separately.

## Independent read-only review

One production writer; three specialists covered the six requested concerns.
All concrete findings were corrected and regression-tested:

- Evidence/false positives: require parent supervision, complete invocation and
  assertion coverage, original/derived source equality, pre-kernel metadata hashes,
  and observed graph start before attributing behavioral failure.
- Compatibility/state: reject raw v2 attestation; bind candidate for failure too;
  enforce result/classification/top-level consistency; rederive every quality axis
  from admitted source facts; keep history and repair routing out of evaluation.
- Publication/surfaces: reject byte-mismatched source copies; keep v2 local and
  GCS publication fenced; expose assertions/environment/mocks/limits/receipt in
  browser text; verify separate evaluation exits and ordinary request rejection.

Final review at `185b073` found no remaining blocker. Reviewers inspected source;
they did not claim independent notebook execution or rerun the complete suite.

## Limits and stop state

This proves only the three declared deterministic fixture behaviors. Live model
classification, live tool/service integration, other architectures, arbitrary user
code, production deployment, restart persistence and general requirements fidelity
remain unverified. Python-process/operator/evaluator trust is explicit; local JSON
IPC, private capabilities and hashes are not hostile-code attestation.

Ordinary CLI/package/API/durable generation remains v1/not_run. API types/browser
support scoped v2 presentation, but no evaluated-bundle lookup or receipt upload
exists. Serialized v2 metadata alone receives limited qualification. No existing
GCS objects or generation-time outcomes are rewritten.

Goal boundary: implementation, local qualification, compatibility documentation,
independent findings and one open PR are delivered. Confidence is high for the
bounded offline fixture path; no production/live qualification is claimed.
Complexity is contained in dedicated admission/bundle owners, with typed shared
derivation and small reader/presentation edits. No second repair loop or stale
quality authority was introduced. Keep the worktree and ignored evidence intact.
