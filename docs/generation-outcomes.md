---
title: Generation outcomes (version 1)
description: Candidate-bound QA qualification, diagnostic artifacts and compatibility.
---

## Generation outcomes (version 1)

Issue #382 separates generation completion, candidate quality, export availability,
and publication. `generation_outcome` is additive. The authoritative derivation
lives in `qa/outcomes.py`; CLI, API and browser consumers use its result.

## Contract

`schema_version` is 1. Overall `status` has deterministic precedence: `failed`
(pipeline failure), `blocked` (current blocking findings), `unverified` (missing
or ambiguous qualification), `advisories`, then `completed`.

- `pipeline`: `completed`, `failed`, or `unknown`.
- `artifacts`: `presence` (`present`, `missing`, `unknown`), `availability`
  (`available`, `not_available`, `unknown`), and scope `generated_output_set`.
  These describe produced files. Current owner access and published object bytes
  remain governed by `artifact_contract` and verified publication receipts.
- `static_qa`: `passed`, `failed`, or `not_run`.
- `environment_smoke`: scope `trusted_smoke_test`; result `passed`, `failed`,
  `unavailable`, or `not_run`.
- `generated_execution`: scope `generated_notebook`, result `not_run`. This
  feature does not execute generated code or implement #381.
- `usability`: `blocked`, `no_known_blockers`, or `unknown`.
- Counts, checks, candidate identity, missing/stale evidence counts, repair
  budget and rollback metadata explain the classification.

`completed` and `no_known_blockers` never establish functional verification.
A trusted kernel smoke, AST validation, valid nbformat, uploaded objects or a
completed worker cannot establish generated-notebook execution success.

Candidate identity is SHA-256 over canonical UTF-8 JSON of the default-composed
notebook's ordered cell types, exact sources and stable metadata, with a versioned
domain prefix. Exclude cell IDs, outputs, execution counts and internally marked
QA/repair summary Markdown cells. Executable cells are always included, even if
their metadata uses a reserved summary marker. The hash input is the bytes
`notebook-cells-v1\0` followed by canonical JSON (UTF-8, sorted keys, compact
separators, exact Unicode sources, no NaN). Notebook-level metadata is outside
this cell identity. Reports bind through `evidence.candidate_id`. Stale evidence
cannot qualify another candidate. Unbound positive reports never establish a pass;
known unbound blockers are conservative failures. `qa_history` is never an input
to outcome derivation.

## Compatibility and exits

Legacy `success` means a result/artifact set was returned or committed, including
diagnostic results. `generation_complete` means the generator packaging boundary
was reached. Neither means usable or verified. `qa_summary.artifacts_usable` is
nullable: true for no known blockers, false for blocked, null for unknown.
Missing checks yield `qa_summary.status=not_run`, rather than `passed`.

Old manifests remain readable without mutation. Missing/unsupported outcomes
project unknown qualification unless existing evidence establishes a blocker.
Diagnostic downloads remain available. SSE completion stays compact and points
to the owner-scoped result URL. A retrieval failure never resubmits generation or
changes a committed job's state.

CLI exits: 0 for completed/advisory/unverified artifact results; 2 for returned
blocked diagnostics (including unavailable live runtime); 1 for generation or
export failures without a returned artifact result. Available paths are printed
before a diagnostic exit. Stub generation retains its shortcut: static QA and
generated execution are not run, usability is unknown.

## Result examples

These are projections of the outcome, rather than complete model instances.
Every row keeps `generated_execution.result=not_run`.

| Evidence and result | Pipeline | Status | Usability | CLI exit |
| --- | --- | --- | --- | --- |
| Candidate-bound static checks pass, files exported | `completed` | `completed` | `no_known_blockers` | 0 |
| Static checks pass with advisory findings | `completed` | `advisories` | `no_known_blockers` | 0 |
| Blocking findings remain after the repair budget; diagnostic files exported | `completed` | `blocked` | `blocked` | 2 |
| Stub shortcut or empty reports; files exported | `completed` | `unverified` | `unknown` | 0 |
| Live runtime is unavailable; diagnostic files exported | `failed` | `failed` | `blocked` | 2 |
| No cells or an incomplete terminal result | `failed` | `failed` | `blocked` | 1 |

A diagnostic API result can contain `success: true` alongside
`generation_outcome.status: "blocked"` or `"failed"`. That means the result was
returned or committed, with available diagnostic downloads. Consumers must read
the outcome to decide how to present artifact quality. A legacy manifest without
this field yields limited, unknown qualification through the shared reader;
known blocking reports still prevent a positive usability claim.

## Repair and publication

Every allowed repair with cells returns through final static and runtime QA,
including the last budgeted repair. The budget gates repair calls, not validation.
Zero budget makes no repair/model calls. Rejected candidates cannot replace
accepted cells or improve their outcome. Exhausted blockers with cells are
diagnostic outputs. Live runtime unavailability remains a pipeline failure and
does not enter repair; cells may still be exported for diagnosis. No cells or an
incomplete terminal result must not produce a success-shaped empty manifest.

Finalize candidate quality before rendering/exporting the notebook, HTML and ZIP.
Finalize file availability from actual outputs before writing the local manifest.
Durable publication retains that quality, verifies immutable data objects, adds
transport receipts and uploads the final manifest last. No self-hash or committed
object rewrite is introduced. A valid diagnostic result commits the existing
durable COMPLETED state and does not trigger quality-induced retries. Provider
authorization and infrastructure failures retain their established policy.

## Verification references

`tests/unit/test_generation_outcomes.py` exercises deterministic derivation,
candidate provenance, compiled graph routing and repair counts, export claims,
legacy qualification and CLI exits. The lifecycle, durable API/artifact and
executable browser suites compare the shared result through publication,
retrieval and rendering. Final commands, counts, exits, environment limits and
independent review evidence are recorded in
[PR #397](https://github.com/dhar174/langgraph_system_generator/pull/397).

Use one production writer and read-only specialists. Preserve frozen durable
schemas, owner access, publication fencing, endpoint isolation, lazy dependencies
and bounded generator state/history. Do not merge, deploy, provision resources,
change IAM or activate durable submissions. Do not close #380 or claim #381.
