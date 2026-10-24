<!-- repo-agent-bootstrap:file-kind=current-plan -->
<!-- repo-agent-bootstrap:provenance=repo-agent-bootstrap@2026-04-16 -->
<!-- repo-agent-bootstrap:managed:start -->
# Current Plan

## Objective and owner decision (2026-10-23)

Reconcile v1.1 tracking against fetched `origin/main`
`4f17c2d06c9156674da394eae7715b656723400a` and merged implementation.
This is the current status matrix; Memory Bank and feature guides link here.
Charles deferred #383: it remains **open, later, and not a v1.1 release blocker**.
Its original usage/price/budget ambitions remain future scope, not delivered work.
No usage collector, pricing engine, per-generation monetary budget or general
token ledger is implemented by this documentation assignment.

## Development order and release gate

1. Retain completed #379 endpoint isolation, #382 truthful outcomes and #381's
   explicit controlled-fixture evaluator. Do not reimplement them because broader
   execution or semantic verification is absent.
2. **Next: #334**, one opt-in Requirements/Domain Fidelity Reviewer. First specify
   typed inputs and findings (constraint/candidate/check IDs, evidence, suggestions,
   source/context references, attempt and reviewer version), gate it off by default,
   and bound calls, input/output, concurrency and time. Disabled/stub paths remain
   offline. First-slice findings are advisory-only: no repair, packaging block or
   automatic semantic rewrite. Compare known fidelity failures and false positives
   using deterministic fixtures before expanding the panel. The umbrella's later
   blocking/repair and docs-alignment acceptance criteria remain required.
3. Keep #129 open for controlled critique/revise versus judge quality comparisons:
   fixed tasks, prompts, rubric, model/version/date, latency and limitations.
   Existing structural examples are not empirical quality results. Provider-reported
   usage may later supplement benchmarks; unknown usage is not zero. #383 is not
   a mandatory prerequisite for #334 or #129.
4. #380 real-cloud staging and owner acceptance remain a separate operational
   track. Keep its remaining child criteria, migration, drain/rollback and real
   IAP/OIDC/Tasks/GCS/IAM qualification visible. No activation is authorized here.
5. #335 multi-tier runtime outer-agent memory remains later, unimplemented scope.
   Contributor memory and RAG caches do not satisfy it. #383 remains deferred.

Epic #378 remains open. Its release-acceptance criterion 5 now requires accurate
cost/usage disclosure and retained bounded-call/resource policies, **not newly
implemented accounting or token-budget enforcement**. The original criterion's
usage ledger, price estimates and budget-stop behavior are preserved under
#383 as deferred scope (decision 2026-10-23). Other release gates remain scoped:
controlled execution is not general prompt fidelity or live deployment acceptance.
See [usage and cost management](../README.md#usage-and-cost-management) for the
interim provider-managed controls; LNF itself has no per-generation spending cap.
`settings.default_budget_tokens` occurs only as a declaration in `utils/config.py`
in production source and is reserved/unenforced. Repair, iteration, timeout,
concurrency, worker-attempt and cancellation limits remain required.

## Capability boundaries

- Ordinary CLI/package/API/worker generation remains v1 with generated execution
  `not_run`; offline stub static QA is also `not_run`, usability `unknown`.
- Explicit approved-fixture evaluation can write separate local v2 bundles with
  candidate/byte-bound execution evidence. Three controlled families (router,
  supervisor and chatbot/tool) and four negative controls do not verify arbitrary
  prompts, live providers/tools, all architectures or general requirements.
- Python network guards and process/resource limits protect trusted fixture runs;
  native networking and user filesystem privileges are not hostile-code containment.
- Local v2 is not an automatically accepted cloud attestation. Durable publication
  rejects those claims; source exports/publications remain unchanged.
- Source review, mocked SDK tests, a real **local Firestore emulator**, real-cloud
  staging and production are distinct evidence levels. Neither merged adapters nor
  emulator success establishes live GCP deployment acceptance.

## Acceptance and disposition matrix

Paths below are relative to `src/langgraph_system_generator/`, unless prefixed
`tests/` or `docs/`. A1, A2, etc. mean the original acceptance bullets in order;
individual criterion decisions and exact test names are recorded in the linked
issue bodies. Required but unlocated validation remains incomplete even where
source implements the intended guard; this task does not add tests or code.
All dispositions refer to merged source, not this unmerged documentation branch.

| Issue / criterion | Implementation files or symbols | Merged delivery | Actual evidence / remaining gap | Disposition |
| --- | --- | --- | --- | --- |
| [#379][i379]: credential/destination/redaction/offline parity | `utils/llm_endpoint_security.py::authorize_endpoint`, `_llm.py::build_chat_llm` | #384, #396 | [Security receipt][security]: final hosted #384 full 1,030 passed/4 skipped; all 113 security cases passed locally. DNS/TLS/egress remain trust assumptions. | Already closed; retain accepted scope |
| #380 Phase A: namespaces, task ownership, SSE bounds | `api/server.py`, `api/progress_streaming.py` | #385 | Final local 1,093 passed/3 skipped; real credential-free concurrent exports/downloads. Final Phase A hosted CI did not run; earlier startup failures are not passes. | Implemented; parent stays open |
| [#386][i386] A1 models; A2-A5 contracts/parity/ADR/selection | `jobs/{models,protocols,registry,service}.py`, ADR 0002 | #392, #394-#395 | Source uses `Literal[1]`/`extra="forbid"`; rejection tests for unsupported schema and secret-bearing extra transport fields were not found. Other contract/import/stub gates: [B1][b1], [qualification]. | Open; A1 validation residual |
| [#387][i387] A1-A7 identity/ownership | `api/{identity,durable}.py`, `jobs/internal_identity.py`; identity/API tests | #392-#395 | JWT/owner/machine tests pass. A2 replacement-key rotation, A3 altered run/artifact parameters, A4 explicit public owner-field rejection and A7 raw assertion/key redaction lack direct tests. | Open; A2/A3/A4/A7 residuals |
| [#388][i388] A1-A7 durable transactions/events | `jobs/{firestore_store,service}.py`; contract/store/emulator tests | #392-#395 | Claims/fences/expiry/outbox and local emulator pass. Concurrent renewals (A2), duplicate append/idempotent event keys (A4) and schema-mismatch tests (A6) remain. `append_event` has no idempotency-key argument. | Open; retain exact criteria |
| [#389][i389] A1-A7 immutable publication | `jobs/gcs_artifacts.py::GCSArtifactStore`; private-artifact tests | #393-#395 | A1 no-shared-filesystem GCS readback and A7 real-GCS preconditions remain unverified. Durable upload symlink protection is source-reviewed; A4 substitution regression not found. Fakes cover other receipt/fence paths. | Open; A1/A4/A7 residuals |
| [#390][i390] A1-A7 dispatch/worker | `jobs/{cloud_tasks_dispatcher,worker,execution,attempt_process}.py`, `api/worker_server.py` | #393-#395 | Fake Tasks/OIDC/GCS, stub bytes, duplicates and deadlines pass. Source enforces 1024-byte payload and `Literal[1]`, but A2 oversized/unknown-version rejection tests were not found. | Open; A2 validation residual |
| [#391][i391] A1-A7 recovery/cleanup | `jobs/{reconciliation,retention,service}.py`, `/internal/reconcile` | #392-#395 | Fencing/retry/cleanup tests exist. A1 complete crash matrix, A2 reconcilers plus renewing worker, A4 persisted-cancellation restart and A6 concurrent cleaners lack direct evidence. | Open; retain validation residuals |
| [#380][i380]: end-to-end durable operational acceptance | `api/durable.py`, `jobs/`, rollout resources/recipes | #385, #392-#395 | [Rollout gates][rollout]: offline/SDK/emulator accomplished; real two-principal IAP/OIDC, GCS/Tasks, IAM/indexes, limits, restart/cancel/cleanup, drain/rollback and owner acceptance outstanding. | Keep open, qualification pending |
| Redaction security follow-up | `utils/credential_redaction.py::_redact_named_credentials` | #396 | Linear scanner and bounded watchdog/progress regressions; [security]. Final-head checks inspected; this is no blanket secret-detector or production claim. | Merged correction; no security-alert state changed here |
| [#382][i382]: independent outcomes, final-candidate QA, diagnostic exports and surface parity | `generator/{outcome_models,graph,nodes}.py`, `qa/outcomes.py`; `tests/unit/test_generation_outcomes.py` | #397 | PR receipt: final full 1,472 passed/8 skipped; SDK 241/241; all-five-architecture stub exports; current candidate and final-repair tests. | Already closed; v1 delivered |
| [#381][i381]: generated behavior, cases, scope, offline controls, coherence | `qa/execution_{evaluation,probe,qualification}.py`, `qa/evaluated_bundle.py` | #398-#399 | [Receipt][execution]: `11ef72a` 102 focused, 3 cases/110 assertions, 4 controls. Full 1,558/7 skips is `185b073`; final hosted checks are separate. | Already closed; controlled-fixture scope |
| [#383][i383]: usage/price/budget infrastructure | Only reserved `utils/config.py::Settings.default_budget_tokens`; no aggregate enforcement | None | Source search finds declaration only; no collector/pricing/ledger or per-generation cap delivered. | Open, deferred, non-blocking |
| [#334][i334]: first semantic reviewer, later panel and repair routing | Existing `qa/registry.py` is an extension seam, not a delivered reviewer | None | Typed, gated advisory-only first slice is next; later blocking/repair and docs-alignment criteria remain. | Open, Ready |
| [#129][i129]: repeatable empirical quality/usage comparison | Existing benchmark examples are structural only | None for complete comparison | Preserve rubric, repeatability, quality, latency and usage provenance; provider usage may supplement later. | Open; no #383 prerequisite |
| [#335][i335]: multi-tier outer-agent memory | Existing RAG/contributor memory does not meet issue | None | Design/backend/retrieval/retention/privacy and runtime integration remain future work. | Open, later |
| Wave 5 #60/#63/#64/#202 | `patterns/{router,critique_loops,subagents,hybrid}.py`, `RequirementsAnalyst.analyze_dialog` | #361 | Historical 167 pattern-focused, 115 generator/API, 646 unit, 764 full/3 skipped; [TASK005][wave5]. Verified merged; no reimplementation. | Complete |

## Merged provenance and review limits

GitHub merged state, actual changed files/diffs, review bodies/threads and available
receipts were inspected. Merge commits below are ancestors of the fetched base.
Review comments and resolved discussions are not an independent GitHub APPROVED
review of every final delivery head. #361 has four unresolved thread flags,
although its final diff includes the reported corrections; no thread mutation
or runtime follow-up is included here. #397 has no submitted GitHub reviews; its
independent review is documented in its receipt/PR. #399's external COMMENTED
review was at `185b073`; final fixes have separate focused/fixture evidence.
Final-head green checks supplement these receipts; titles/check color alone are
not the acceptance basis. No new runtime/model/cloud tests were run for prose.

| PR | Merge commit | Delivery head (not necessarily the receipt's tested SHA) |
| --- | --- | --- |
| [#361](https://github.com/dhar174/langgraph_system_generator/pull/361) | `5c239e59dcaf1aca2b32ea762a4cf110d188ba45` | `136c46a7bcbba92dc5c6a404784dffb16fed1c5a` |
| [#384](https://github.com/dhar174/langgraph_system_generator/pull/384) | `11551ab9e36cca3f1948db486b4267ee7895dc8c` | `e3cdddc3a215ea07e823b53a4e260905b51b795e` |
| [#385](https://github.com/dhar174/langgraph_system_generator/pull/385) | `60e205b7e9d80c31a57de5601d8ab4789045823c` | `d1b825fcb8be7650e59abd91fe1399328afba83d` |
| [#392](https://github.com/dhar174/langgraph_system_generator/pull/392) | `305274f7eca82655e3556b2df50f0406f2d7905c` | `e988165aa2c4a2bc2a65db6a0163ecfbdf0c2c20` |
| [#393](https://github.com/dhar174/langgraph_system_generator/pull/393) | `101f14fcf2ab009360a2562181521c6aeb531ea0` | `fccdee3e6283255f8d3b69a6e783f05775eaaa2d` |
| [#394](https://github.com/dhar174/langgraph_system_generator/pull/394) | `6b0348783a0ee141608466bf928884179e7ede38` | `54c3060b65cfa388f0c183449afe067fba0522d9` |
| [#395](https://github.com/dhar174/langgraph_system_generator/pull/395) | `a5851a4f5d540d581384900aa83659d7c0797e08` | `feb456d3913e743e48a3939642d215840cfd3d1c` |
| [#396](https://github.com/dhar174/langgraph_system_generator/pull/396) | `223f6ade1592dacd88c8efbd32ec106d48c8293b` | `1bd3417442041b805cfb335c1b3ff84cbb3759ef` |
| [#397](https://github.com/dhar174/langgraph_system_generator/pull/397) | `9cb1aadba2c9aab25f988591bed32504fe206483` | `8a61a220030698ff49f74ffcfe0589794f745050` |
| [#398](https://github.com/dhar174/langgraph_system_generator/pull/398) | `d599e602272261d38516d121ff02b61643c29c8b` | `20e0c4af297b2b1840a30487b85c6f653ddae8af` |
| [#399](https://github.com/dhar174/langgraph_system_generator/pull/399) | `4f17c2d06c9156674da394eae7715b656723400a` | `91bf5da0b4c96af208b892eb7454d03872f4fdb1` |

The [postmerge qualification receipt][qualification] reports core **64/64**, SDK
**223/223** with zero skips, emulator **4/4 in each of two namespaces** at
`d522131`, plus unit **1,208 passed/1 optional PDF skip**, patterns **82 passed**
and full **1,326 passed/8 skipped**. Later #397/#399 qualification has its own
heads/counts. Broad static baseline failures remain failures, not passing gates.
Dated receipts are preserved without relabeling tested commits as merge commits.

## Existing Project and issue housekeeping

Use [dhar174 Project #3](https://github.com/users/dhar174/projects/3)'s existing
Status, Priority and Notes fields. No new field taxonomy, dates, epics or projects.
Previously accepted closed implementation (#379/#381/#382) remains Done; #334
is Ready/next; #383 is Backlog/deferred/non-blocking; #335 Backlog/later;
#380 In progress/qualification pending. #386-#391 remain In progress with their
criterion-level validation residuals;
this reconciliation closes none of them.
#378 remains open/In progress. #129 remains open for controlled comparisons.
No scoped issue currently has a milestone, and dependency API reads found no
formal #383 blocker edges; remove contradictory prose dependencies instead.

Older clusters are **triage only**, with no state changes in this reconciliation:

- #3: map the seven historical phases to current modules and evidence in a later
  audit; do not execute its original phase plan anew or close it wholesale.
- #23-#27: #25 is already closed. Convert the remaining broad update/investigation
  requests into versioned residual criteria after source/docs review; avoid
  blanket "latest everything" upgrades or duplicate implementation.
- #59: compare each child against the registry-backed pattern modules and merged
  Wave 5 before proposing individual dispositions. Its old `patterns.py` path is stale.
- #70/#84/#85: require notebook cell/state and UI behavior evidence, including
  non-default inputs and Run All/error fallback. PR #367 remains open and overlaps
  activeContext, but includes unrelated contributor-asset deletions; do not merge
  or close it here. Reassess its narrow useful fixes separately.
- #376: scope a version/date/source-backed guide and cached-doc refresh separately;
  this roadmap reconciliation does not certify every legacy guide/example.

Open PRs #373 (missing-implementation report), #372 (memory generation), #367
(CYOA), #316 (activity reports) and #313 (diagram) were inspected for overlap.
Their content is not current capability evidence and none was modified.

## Documentation validation and handoff

Only the assigned documentation surfaces and `.env.example` comments may change.
Run the documentation workflow's `tests/unit/test_documentation_coverage.py`,
local Markdown target checks, `git diff --check` and an exact conflict-marker
scan. Check that no runtime/test/dependency/lockfile/workflow/deployment values
changed. Preserve managed markers and historical receipts. Re-read each issue and
Project item immediately before mutation and verify all writes by readback.
Publish one documentation PR, link it from reconciliation comments as unmerged
proposed docs, obtain read-only closure/capability review and stop before merge.

[i379]: https://github.com/dhar174/langgraph_system_generator/issues/379
[i380]: https://github.com/dhar174/langgraph_system_generator/issues/380
[i381]: https://github.com/dhar174/langgraph_system_generator/issues/381
[i382]: https://github.com/dhar174/langgraph_system_generator/issues/382
[i383]: https://github.com/dhar174/langgraph_system_generator/issues/383
[i334]: https://github.com/dhar174/langgraph_system_generator/issues/334
[i129]: https://github.com/dhar174/langgraph_system_generator/issues/129
[i335]: https://github.com/dhar174/langgraph_system_generator/issues/335
[i386]: https://github.com/dhar174/langgraph_system_generator/issues/386
[i387]: https://github.com/dhar174/langgraph_system_generator/issues/387
[i388]: https://github.com/dhar174/langgraph_system_generator/issues/388
[i389]: https://github.com/dhar174/langgraph_system_generator/issues/389
[i390]: https://github.com/dhar174/langgraph_system_generator/issues/390
[i391]: https://github.com/dhar174/langgraph_system_generator/issues/391
[security]: ../docs/llm-endpoint-security.md
[b1]: ../docs/verification/2026-10-20-b1-durable-contracts.md
[b2]: ../docs/verification/2026-10-20-b2-managed-execution.md
[qualification]: ../docs/verification/2026-10-21-durable-postmerge-qualification.md
[execution]: ../docs/verification/2026-10-23-381-b-execution-outcomes.md
[rollout]: ../docs/durable-api-rollout.md#owner-acceptance-matrix
[wave5]: ../memory-bank/tasks/TASK005-pattern-intake-modernization-wave.md
<!-- repo-agent-bootstrap:managed:end -->
