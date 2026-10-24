# #334-A: bounded advisory Requirements/Domain Fidelity Reviewer

Approved 2026-10-23 in the assignment conversation. Base: fetched main
`96baddc5768df5d5bbb06b47568f94ffccca4857`; #397-#400 are merged.

## Goal and architecture

Deliver one opt-in runtime product reviewer, offline tests, documentation and one
unmerged PR. Use the existing shared generation pipeline and authorized model
factory. Add an async specialist seam alongside synchronous QA registrations;
never run network calls inside NotebookValidator or deterministic repair.

## Contract and owners

- `qa/specialist_models.py`: frozen policy, context, evidence and result types.
- `qa/specialist_review.py`: complete redacted composed-candidate context,
  evidence admission and QA conversion; keep nodes focused.
- `generator/agents/requirements_reviewer.py`: prompt and one direct async
  structured model call. Registry supplies a lazy factory and async interface.
- Graph entry snapshots Settings mode/plugin policy per invocation; the final
  eligible candidate passes through semantic review after deterministic repair
  settles. Failure packaging and final-repair validation remain intact.
- `LNF_SPECIALIST_QA_MODE=off|advisory`, default off. No request field or UI toggle.
  Separate workers read their own configuration; durable schemas stay frozen.

Original prompt/dialog remain fidelity authority even if intake misses a
requirement. Include constraints, feedback/conflicts, architecture/plans, exports,
context pack, supplied docs and every composed candidate cell. Assign stable
requirement/cell/docs IDs and host fingerprints, candidate notebook-cells-v1 ID,
attempt and complete redacted envelope digest. References use canonical candidate
cell indices, redacted character ranges and exact quotes; docs provenance/version
is supplied, never invented. Invalid evidence rejects the entire response;
candidate/context changes invalidate admission without a replacement call.

## Bounds, failure policy and compatibility

One invocation, zero retries/fallbacks/tools/retrieval/execution, 30-second deadline
(Python 3.10-compatible cancellation), <=48,000 serialized input characters
including instructions/schema, output <=min(request cap,2048) tokens, raw response
<=16,384 characters, <=8 findings. Messages <=400 chars; <=2 suggestions of <=240
chars; <=6 references/finding, <=2 per family; quotes <=160, ranges <=2000 chars.
Reject over-limit input as incomplete without dropping cells. Retain max_retries=0,
endpoint authorization, redaction and local transport cleanup. Propagate caller
cancellation; no detached work. Suppress local tracing/callback/cache retention.

Feedback distinguishes disabled, skipped, reviewed, unavailable, invalid_response,
incomplete with stable reasons. No findings means only model-reported no concerns.
Missing docs mean docs alignment not assessed. Persist sanitized summaries and
IDs/ranges/fingerprints, never prompt/raw response/quotes. Findings become
candidate-bound semantic warning QAReports, never repairable. Do not modify
executable cells, plans, architecture or repair attempts. History is not authority.

Optional qa_summary.semantic_review projects through CLI/API/browser and existing
derived outcome Markdown before export/publication; escape model text. Off omits
new fields. Frozen v1/v2 outcomes, execution not_run, #381 authority/dataset/digest
and requirements unverified remain intact. No hash exclusion expansion or object
rewrite. Advisory/review failure cannot cause durable retry or quality exit.

These are review-call controls, not whole-generation cost/token enforcement.
default_budget_tokens is not repurposed. Durable re-execution can review again.
Blocking semantic review, semantic repair, panel, #129 benchmarks, #383 ledger and
#380 staging remain deferred/separate. Do not create issues, close #334, merge,
deploy or enable hosted configuration.

## Implementation and verification sequence

1. Establish baseline tests; add typed context/evidence contract and focused tests.
2. Add bounded direct reviewer and request-capture tests (actual HTTP counts).
3. Extend registry and graph; test final repaired candidate, skip paths, isolated
   policies, stale results, cancellation and unchanged repair/plugin behavior.
4. Project feedback safely through existing summaries and exports. Test package,
   API/browser and durable immutable publication/no-retry paths.
5. Add six labelled corpus cases (clean/domain/missing behavior/prose-only tool/
   provided-docs conflict/insufficient context). Fakes prove contracts, not accuracy.
6. Update README, .env.example, QA/architecture docs and concise advisory-only ADR.
7. Run focused, unit, patterns, full suites; credential-free durable SDK/security/
   outcome/evidence/browser regressions, actual stub and fake-review exports;
   verify nbformat v4, candidate IDs, ZIP/manifest/files/downloads and safe prose.
8. Focused Ruff/Black/mypy, fatal Flake8, JS syntax, diff/conflict checks; compare
   broad debt to exact base with command/output/exit/source receipts.
9. Independent read-only review of bounds/evidence/async/privacy/rendering/output
   truth. Resolve blockers, publish/attach one PR: Part of #334; Related to #378.

Official ChatOpenAI model/structured-output docs informed design; installed
langchain-openai 1.7.2 and fake-transport tests decide compatibility. Use explicit
native response_format and local validation to avoid helper method fallbacks.
No dependency upgrades for a convenient API and no live paid evaluation.

Complexity: nodes/CLI are large integration owners. New cohesive modules own
context, admission, model call and rendering; existing owners receive narrow
delegation only. No unrelated refactor or second production writer.
