# #381-B execution outcome integration

Approved plan: explicit repository evaluator only; version-1 preservation,
candidate-bound version-2 evidence, separate receipt and new local presentation
bundle. Baselines acknowledged: PR #398 at 20e0c4a, PR #397 at 8a61a22,
generation-outcomes and generated-notebook-evaluation guides, outcome/state/QA
and immutable publication owners. No missing authority references.

Canonical owner: shared qa/outcomes derivation. New focused owners handle receipt
admission and local evaluated bundles. API/worker execution and cloud evaluation
storage remain outside this change. One production writer with read-only review.

Complexity check: avoid adding evaluator logic to large generator/CLI handlers;
small typed reader/presentation edits there, new admission/bundle modules. No
second repair engine or history-based qualification.
