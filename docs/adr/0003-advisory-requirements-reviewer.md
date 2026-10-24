# ADR 0003: advisory final-candidate requirements review

Status: accepted for #334-A, implementation gated by operator configuration.

## Decision

One Requirements/Domain Fidelity Reviewer runs after deterministic QA/repair
settles, before packaging. It is a runtime product agent, not a contributor asset.
`LNF_SPECIALIST_QA_MODE` accepts `off` (default) or `advisory`. Mode and plugin
configuration are snapshotted for each invocation. A separate worker reads its
own configuration; setting the API process does not configure a worker.

The synchronous validator/repair registry gains a separate async specialist seam.
Configured plugin modules are administrator-trusted executable code, as for the
existing validator/repair extensions; replacements must honor this contract.
The built-in reviewer makes one direct model call with the resolved authorized
provider/model and a copied output cap. No tools, retrieval, execution, autonomous
loop, correction retries, model fallback or semantic repair is available.

## Bounds and evidence

Review deadline: 30 seconds, subordinate to enclosing cancellation/deadlines.
Input: <=48,000 serialized Unicode characters including instructions and response
schema. All candidate cells must fit; oversized input yields incomplete review.
Output: <=2048 tokens or a stricter request cap; raw response <=16,384 characters,
at most eight findings. Messages <=400 chars, at most two <=240-char suggestions,
at most six references (two per family), quotes <=160, ranges <=2000 characters.
Persisted source locations are <=512 characters and supplied versions <=128;
unrepresentable reference metadata invalidates admission rather than being clipped.

The original request remains fidelity authority. The host owns notebook-cells-v1
candidate identity, complete redacted envelope digest, attempt, reviewer version
and source IDs/fingerprints of the exact redacted source view. The existing
candidate algorithm separately binds the original candidate. Requirements, canonical candidate-cell indices and
supplied docs references are validated before findings are admitted. Quotes and
raw review payloads remain transient; only bounded sanitized summaries and
IDs/ranges/fingerprints persist. A matching quote proves provenance, not judgment.
Missing docs mean docs alignment not assessed. Untrusted input delimiters and
rubric instructions reduce exposure, not universal prompt-injection resistance.

## Why advisory first

Static validity, execution under controlled fixtures and semantic opinion are
different evidence. This reviewer can identify concerns but cannot prove fidelity.
Warnings cannot block packaging, route to repair or retry durable generation.
Reviewed/no-findings is a model report, never requirements verified. Unavailable,
invalid and incomplete reviews remain explicit. Existing deterministic blockers
and frozen v1/v2 execution qualification keep their existing meaning.

Alternatives deferred: a blocking semantic gate, semantic repair loop and panel.
Those require separately accepted policy and repeatable failure/false-positive
evidence under #334/#129. The small labelled corpus tests contracts, not accuracy.
No live review or empirical quality-improvement claim is part of this delivery.

## Operational limits and compatibility

These limits bound this review call, not whole-generation tokens or money.
`default_budget_tokens` is not enforced by this feature. Use provider spend
controls/quotas/alerts operationally, subject to their scope and enforcement lag.
#383 usage accounting/pricing/budget stops remain deferred and non-blocking.
Durable re-execution starts a fresh invocation and may repeat the provider call;
there is no exactly-once provider-use or billing promise.

Feedback is finalized before export and immutable publication. It uses existing
QA reports/summary and derived Markdown; code and hash exclusions stay unchanged.
No public request field, model routing platform, receipt-upload route, UI toggle,
durable request migration, deployment or hosted enablement is introduced. Default
off omits new output fields and constructs no reviewer/client. Stub remains offline.
#381 evaluator authority/dataset/digest and #380 staging gates remain unchanged.

Syntax references: official [ChatOpenAI structured output](https://docs.langchain.com/oss/python/integrations/chat/openai#structured-output)
and [standalone model usage](https://docs.langchain.com/oss/python/langchain/models).
Installed APIs and credential-free request-capture tests determine compatibility;
the native schema request is direct to avoid helper method fallback/correction.
