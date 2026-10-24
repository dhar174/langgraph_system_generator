# #334-A offline verification

Base: `96baddc5768df5d5bbb06b47568f94ffccca4857` (fetched main; #397-#400 merged).
Scope: one operator-opt-in advisory runtime reviewer. Part of #334; related to
#378. #383, semantic blocking/repair/panel, #129 broad empirical benchmarks and
#380 staging gates remain deferred. No merge, deployment or hosted enablement.

## Implementation and review

`RequirementsDomainReviewer.review` makes one direct authorized async model call;
the async registry seam preserves synchronous deterministic registrations, cloning
and ordering. `review_policy_node` snapshots operator policy at graph entry;
`semantic_review_node` runs after final deterministic validation and before export.
Context/admission and presentation each have a separate small module. Current
candidate reports retain static/runtime evidence and bounded history.

Hard bounds: one call per generator invocation, zero SDK/correction/fallback
retries, 30 seconds subordinate to enclosing cancellation, complete serialized
input <=48,000 Unicode characters, output <=min(request cap,2048) tokens, raw
response <=16,384 characters, eight bounded findings. Invalid references reject
the response. Quotes/raw inputs/responses remain transient; accepted locations,
versions, IDs/ranges/fingerprints and sanitized summaries persist.

Independent read-only reviews covered call limits, final-candidate evidence,
async/cancellation, endpoint credentials, stage ownership, rendering and output
truth. Concrete issues fixed and re-reviewed: inherited tracer callbacks, raw
source fingerprints and missing persisted source locations. Mixed-policy
concurrency coverage was added. No remaining concrete built-in blocker reported;
administrator-configured plugin modules remain trusted executable code.

## Environment and receipts

Windows, Python 3.12; task-private system-site-packages environment at
`output/verification334/venv`. Installed this checkout with declared `[gcp]`
extras and psutil for qualification. Inherited nbconvert lacked template assets;
reinstalled the same nbconvert 7.16.6 into the private environment. Repository
dependencies/lockfiles were not changed. Installed APIs, rather than convenience
API assumptions, determine compatibility: langchain 1.4.6, langchain-core 1.6.12,
langchain-openai 1.7.2, langgraph 1.2.16, openai 3.35.1, pydantic 2.14.1,
pydantic-settings 2.16.1, nbformat 5.11.1 and nbclient 0.11.0.

Task-local `run_check.py` clears inherited provider credentials/dotenv/tracing,
runs each command and retains command/cwd/start/end/PID/exit/source SHA256 map,
stdout and stderr in ignored `output/verification334/*.receipt.json` and sibling
logs. These local logs are not uploaded artifacts or committed source evidence.
Final readback compared all 209 recorded source/test/script files for the unit,
full, execution-recheck and SDK receipts against delivery source: no mismatches.
Documentation-only handoff edits followed; no executable source changed after
those gates. Earlier focused/static/artifact checks are separate checkpoints.

## Observed checkpoints

| Check | Observed result |
| --- | --- |
| Focused semantic contracts/provider/pipeline/durable/corpus/browser | 71 passed, exit 0 |
| `python -m pytest tests/patterns/ -v` | 82 passed, exit 0 |
| First unit attempt | 1508 passed, 1 failed: API test fixture inherited shutdown state; fixed fixture setup |
| Second unit attempt | 1510 passed, 1 failed: Windows PermissionError renaming existing publication-test directory |
| Entire affected lifecycle module recheck | 65 passed, exit 0, no source change |
| Final `python -m pytest tests/unit/ --asyncio-mode=auto -q` | 1511 passed, exit 0, 371.98s |
| Full `python -m pytest --asyncio-mode=auto -ra` | 1629 passed, 1 failed, 7 skipped, exit 1, 895.46s |
| Unchanged execution integration recheck | 1 passed, exit 0, 216.43s |
| `scripts/qualify_durable_backend.py --level sdk --test-timeout 900` | 243 passed, no skips, exit 0 |
| New-module focused Ruff / Black / mypy | Exit 0 |
| Fatal Flake8 `E9,F63,F7,F82`, JS syntax, diff whitespace | Exit 0 |

Actual SDK tests use httpx MockTransport: success, HTTP 400, 429 and 500 each
produced exactly one HTTP request. Native schema, zero retries, copied output cap,
no tools, `store=False`, timeout/cancellation transport cleanup and no inherited
tracer/collector persistence were checked. Enabled final-candidate graph tests
performed two deterministic repairs followed by one review with no extra repair.
Off/stub/blocker/no-cell paths construct no reviewer or client.

The full-suite failure is the existing generated-execution integration's
nontermination control: child kernel fixture-support import exceeded its existing
20-second bootstrap limit before reaching the intended graph loop. All three
clean fixtures and three other controls passed; all child cleanup was verified.
No timeout, evaluator assertion, dataset or digest was changed. The exact
integration recheck passed without source changes. This does not relabel the
failed full-suite run as green. Full-suite skips are four
opt-in Firestore emulator cases and three opt-in packaging install cases.

Durable semantic tests exercise the real attempt/shared-generation/worker/result
path with SDK-shaped in-memory fakes for both memory/Firestore store choices.
Advice/unavailability does not start another whole-generation attempt; redelivery
does not rewrite immutable objects. This is offline qualification, not staging.

## Artifact smoke evidence

Credential-free stub CLI export and actual compiled-graph fake-review export both
exited 0. Readback checked nbformat v4, manifest/notebook candidate identity, files,
HTML and ZIP content equality. API tests additionally checked registered downloads.

- Stub candidate: `6156e684c0786ac31d99fff14f92789639a92eebf3fda84b956875fe62176487`.
- Fake-review candidate: `f64c5c532458f23a6381a3f2c06dbab32bcee837b01411833024cbd83320ffe2`;
  25 cells, one review call, reviewed/advisories. Generated execution remains
  `not_run` and requirements remain unverified.
- Approved #381 dataset SHA256 remains
  `913aa00c5c2ce30527ccbc31c1f8263a3ab798560e4a569ca13fb0642b0dfb47`.

## Existing static debt

Compared an archive of the exact base against this source with the same tools.
Broad Ruff exits 1 with 1244 diagnostics on both; broad mypy exits 1 with 107 errors
in the same 16 files on both; explicit-file Black exits 1 with the same 77 files
requiring formatting. Normalized relative-file/code/message multisets have no
added or removed diagnostics. No unrelated formatting was applied. An earlier
zero-file Black run was invalid coverage due to ignored parent path and is excluded.

## Handoff boundaries

Aegis verification discipline keeps offline contract evidence separate from live
review accuracy and release authority. The six-case canned corpus proves plumbing
and evidence rejection, not semantic quality improvement. No live paid model,
cloud staging, provider billing/quotas experiment or deployed feature was exercised.
Provider controls remain operational; local caps constrain this review call only.
Durable re-execution is a fresh invocation and may repeat a provider call.

Architecture alignment: shared pipeline and existing QA/export owners retained;
frozen outcome/durable schemas, #381 trust boundary/dataset, candidate algorithm
and hash exclusions unchanged. ADR 0003 records the advisory tradeoff; AGENTS,
QA and architecture documentation provide the matching current-state baseline.
No duplicate QA authority or semantic repair owner remains. Existing validators,
repairs and execution qualification are intentionally retained by contract.

Complexity increases through four cohesive source modules (55/146/186/448 lines)
and a minimal registry extension (+99 lines); no file newly crosses 800 lines.
Existing large CLI (2291 lines, +29), nodes (1485, +40) and state (932, +6) remain
integration owners with narrow calls into the new modules. The largest new block,
`review_candidate`, owns only invocation/admission orchestration. No additional
panel, usage ledger, routing layer or generic agent framework was introduced.
Confidence: B for bounded offline behavior; live reviewer accuracy and cloud
staging are unassessed, and the full-suite bootstrap timeout remains a recorded
host reproducibility limitation despite the passing isolated recheck.
