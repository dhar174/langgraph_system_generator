# TASK009 - Execution outcome integration (#381-B)

**Status:** Completed (PR #399 merged at `4f17c2d`; #381 closed for controlled-fixture scope)

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

Final implementation source: `11ef72a387a5d58960e59599213895b45a951e8d`.
At checkpoint `185b073`, full suite 1,558 passed/7 optional skips; patterns 82
passed; SDK 243/243 with zero skips. Actual qualification passed all three cases
(110 assertions) and all four
negative controls. Original bytes, receipt/inventory hashes and notebook/HTML/ZIP
prose were verified. Independent findings are resolved, including all reader axes.
All eight hosted checks passed on checkpoint `185b073` and documentation head
`7efb574`. External review then found capture-limit misattribution and unignored
output self-dirtying. Both were fixed at `11ef72a`: 102 focused tests passed,
three fresh real cases passed 110 assertions and all four controls, and the
artifact checker passed again. Read-only review found no blocker in those fixes.
Final hosted status is recorded separately in PR #399; do not relabel receipts.
Maintained evidence: docs/verification/2026-10-23-381-b-execution-outcomes.md.

Current-status annotation (2026-10-23): PR #399 merged at
`4f17c2d06c9156674da394eae7715b656723400a`. #381 remains closed for the
accepted controlled-fixture evaluator. Local v2 is not cloud attestation or
general requirements verification. Counts above retain their tested SHAs.
See [the current plan](../../plans/current-plan.md).

Historical delivery boundary: one open PR; no merge, deployment, cloud
configuration or issue changes were performed by that implementation task.
