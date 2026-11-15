# Proposed holdout for the reviewer rubric revision

Compare the current v2 rubric from merge commit
`da63e61b925389877b29c3986e61451c589e6c62` with the v2.1 rubric from the
accepted revision of this PR. Both use the same excerpt ID protocol, evidence
admission checks, and model settings. The five owner-rejected findings from the
previous study are now development cases. That study remains the historical
comparison. This proposal covers preparation and offline verification.

## Fresh corpus

Author eight unseen clean/defect pairs and four guardrails. Use distinct
requirements, candidate identities, and domains or tasks from the previous
study. Within each pair, keep the request and input contract identical and
change one reachable behavior. Use two pairs for each of these four checks:

1. Different output structures that still satisfy the stated contract, paired
   with implementations that lose the required association or field.
2. Workflows that produce results when called, paired with reachable paths
   that drop supplied input or omit a required result.
3. Deliverable scope, paired with candidates that omit a requirement that the
   request explicitly states.
4. Non-obvious code behavior such as duplicate handling or branch precedence,
   paired with an implementation that fails on a concrete boundary input.

Freeze a concrete witness input and expected behavior for each pair. Keep
witnesses, labels, rationales, mutation metadata, and answer-bearing case IDs
in evaluator-only files. Freeze the required behavior before a human sees the
reviewer outputs. Have an independent reviewer check the labels against
reachable candidate code and saved deterministic QA. Record the reviewer type
and flag genuine scope ambiguities before freezing.

Include guardrails for an underspecified request, an embedded instruction with
a synthetic credential marker, a long request that fits in both arms, and an
oversized request that fits in neither. Keep all 16 paired candidates within
48,000 serialized characters in both arms. Record measured sizes and skip
reasons per arm. Run production static QA and both pinned reviewer paths with
fake transport. Check exact candidate and schedule equality and enforce the
input limit, redaction, and the output contract before requesting approval.

## Proposed live bounds

Use the same frozen candidates in both arms with two repetitions per case and
global concurrency one. Run v2 first, then v2.1, in the same fixed case-ID order.
Record this fixed arm order as an interpretation limit. Proposed ceiling is
**76 provider requests** out of 80 slots, with the oversized case blocked in
both repetitions of both arms. The exact verified ceiling can be lower.

Use `POST https://api.openai.com/v1/responses` with `gpt-6-luna`, low reasoning,
local endpoint policy, and `store: false`. Use a 30-second per-call timeout,
48,000 serialized input characters, 2,048 output tokens, zero retries, and a
41-minute overall deadline. Send only the redacted synthetic request,
candidate content and provided fixture context, plus the pinned instructions
and response schema. Keep labels, credentials, and private inputs out of the
model request body and evidence. The supported local key is for authentication.
Bind both arms to a single reviewed launcher and one-use claim. Stop on
unexpected destination, canary disclosure, authorization or configuration
failure, exceeded limits, or cancellation. Preserve the attempt journal and
leave an interrupted experiment stopped.

## Decision criteria

Blind arm identity during human adjudication where practical. Score paired
clean false positives over all 16 clean trials, confirmed reference recall
over all 16 defect trials, valid reviews over all 32 paired trial slots, and
admission failures over requests. Report outcome transitions by matched slot,
reviewed-only false positives alongside the fixed denominator, unique defects,
per-repetition variation, guardrails by arm, latency, and available usage.
Keep unresolved findings pending and avoid interpreting incomplete adjudication
as a zero rate.

Proposed evidence threshold for retaining the new rubric is all three:

- At most 2/16 clean false-positive trials, and fewer than unchanged v2.
- At least 14/16 confirmed defect trials detected, with at most one fewer hit
  than unchanged v2.
- At least 30/32 valid paired reviews, with at most one fewer valid review
  than unchanged v2.

These are decision thresholds for this small holdout. Keep the default-off,
advisory policy. A missed threshold or unresolved result calls for diagnosis
before another change.

Before any provider call, freeze the accepted source and exact candidate files,
label review, arm plan and launcher hashes, endpoint fingerprint, case IDs,
dispatch order, repetitions, verified attempt ceiling, and transmission scope.
Verify the one-use launcher and both fake transports offline, then request
explicit approval of the final execution digest.
