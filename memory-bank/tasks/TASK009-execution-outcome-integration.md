# TASK009 - Execution outcome integration (#381-B)

**Status:** In Progress

**Added:** 2026-10-23

**Updated:** 2026-10-23

Approved plan: explicit trusted evaluator only, sanitized receipt plus new local
bundle, original artifacts unchanged. Base d599e602; #381-A PR #398 head 20e0c4a.
The unrelated Resource R1 branch in the assignment is not a prerequisite.

## Contracts

- Ordinary generation writes v1/not_run; local explicit evaluation writes v2.
- Only current parent-supervised typed evidence qualifies the selected candidate;
  serialized receipts and qa_history cannot mint execution authority.
- Execution, static QA, environment smoke, generation and availability are distinct.
- Exact executed bytes and presentation derivatives have separate hashes while
  sharing notebook-cells-v1 identity. Original publication facts remain immutable.
- Durable publisher rejects v2 claims. No API/worker execution or new cloud lane.

## Progress

Implementation and focused tests are present. Independent findings addressed
reader trust, stale failure classification, contradictory models, byte mismatches,
and pre-graph errors. Full verification and final review are pending; maintained
evidence: docs/verification/2026-10-23-381-b-execution-outcomes.md.

Stop: one open PR; no merge, deployment, cloud configuration or issue changes.
