# Semantic reviewer quality study

The #334-B study measures how well the advisory Requirements/Domain Fidelity
Reviewer identifies issues in a fixed set of notebook candidates. The reviewer
runs after final candidate selection. It produces advice and leaves the
candidate unchanged. The study reports detection value alongside deterministic
QA. Generated notebook execution and outcome qualification use the separate
[#381 evaluator](generated-notebook-evaluation.md).

The corpus contains eight clean and defective pairs in four domains, plus four
cases for insufficient requirements, oversized input, adversarial instructions,
and realistic context near the input limit. Each pair belongs entirely to
development or holdout. Report guardrail cases separately and freeze the
reference labels, reviewer instructions, and response schema before a pilot.
Use a new holdout for any later study that tunes on these results.

The candidate recipes use public synthetic inputs. For generator-derived
notebooks, the original bytes and altered copies have separate identities.
Production static QA runs on each candidate. Runtime checks omitted by the
fixture recipe provide no runtime evidence. Candidates blocked by static QA
remain visible in the skip stratum.

Each clean member satisfies its pair's focal requirement. It can still
contain an independently confirmed additional concern. The score records
such cases separately from the fully adjudicated clean denominator and
distinguishes concerns already detected by deterministic QA.

## Local workflow

Use the script from the repository root in an environment with the project
dependencies installed.

~~~powershell
python scripts/evaluate_semantic_review.py plan --model gpt-6-luna --output output/semantic-plan.json
python scripts/evaluate_semantic_review.py dry-run --plan output/semantic-plan.json --output output/semantic-dry-run.json
~~~

The command writes JSON evidence and a Markdown plan beside it. Use fresh
output paths for each run.

The plan reports the effective model and endpoint policy, fixture identities,
input sizes, limits, order, repetitions, and maximum attempts. It makes no
provider requests. The dry run uses the production context builder, reviewer,
client factory, and evidence admission with a fake HTTP transport. Its receipts
are labelled **synthetic-contract**. They demonstrate the evaluation
mechanics. **Live reviewer quality has not been measured.**

The proposed live pilot uses the official OpenAI Responses endpoint,
`gpt-6-luna`, low reasoning, concurrency one, two repetitions of 20 cases,
and up to 40 attempted reviewer invocations. Production skips and input
limits can reduce the provider request count. An operator must review the
exact plan and separately authorize execution. This PR leaves the pilot
unexecuted.

The future `run --live` command requires the reviewed plan and its digest.
Changes to the source, dataset, labels, instructions, schema, dependencies,
model, endpoint, caps, repetitions, or retry policy invalidate the plan.
Generate a fresh plan from the exact checkout and environment that would run
the pilot. The checked-in sample plan records its tested source revision.
Each attempt is recorded before dispatch. Interruptions leave the request
uncertain, and the tool never automatically resends it. Provider unavailability,
authentication, configuration, and privacy failures stop the run. Invalid
reviews remain observations. A call ceiling does not guarantee a spend ceiling.

## Adjudication and interpretation

Score the dry-run receipt using the same frozen corpus and labels.

~~~powershell
python scripts/evaluate_semantic_review.py score --receipt output/semantic-dry-run.json --plan output/semantic-plan.json --output output/semantic-score.json
~~~

For a separately authorized pilot, pass the adjudicator's versioned input via
`--annotations`. Keep the initial verdicts and any adjudication revisions with
the associated receipt so disagreements remain inspectable.

The annotation JSON uses `schema_version: 1`, an `annotation_version`, the
byte hashes `dataset_sha256`, `labels_sha256`, and `receipt_sha256`, and an
`annotations` array. Each row identifies a receipt finding by `case_id`,
`repetition`, and `finding_id`. Include `reviewer_identity`,
`reviewer_type`, `verdict`, and `rationale`. A supported verdict includes
`matched_defect_id`. Give votes distinct `annotation_id` values so a human
adjudicator can retain them and add a row with `resolution: true` and
`resolves_annotation_ids` listing the votes it resolves. Record claims
beyond the reference labels as additional concerns with their own IDs and
deterministic QA comparison.

The reference labels are AI-authored and carry separate independent review
records. A human should review the labels and resolve disagreements before
approving the pilot. For each admitted finding, an independent adjudicator
compares the finding with the reference requirement and the redacted source
locations. They record a supported, unsupported, ambiguous, or pending verdict,
the matched defect when applicable, their identity/type, and the rationale.
A category match alone cannot resolve a finding. One defect can count at most
once per trial.

The score includes all selected trials, including abstentions, failures, and
trials that never dispatched. Clean-case false positives use both the eligible
population and the fully adjudicated valid-review subset. Defect detection
includes every eligible defect in its denominator. Precision requires
independent resolution of the findings. Undefined ratios are N/A. The report
also shows invalid references, duplicates, missing-docs behavior, latency sample
counts, and confirmed concerns that deterministic QA missed. Disabled review
has zero semantic findings and zero reviewer calls.

Receipts store safe admitted findings, hashes, provenance, status, and timing.
Use the versioned fixture to reconstruct the reviewer input for inspection.
Evidence references bind to the redacted text seen by the model. A hash binds
the receipt to evidence and does not certify its authenticity or quality.
The named Luna alias may change over time. Record the requested and reported
model IDs and the run date. A 20-case study is descriptive and cannot justify
general production accuracy, automatic blocking, or an improvement to generated
notebook quality.

See the [offline verification receipt](verification/2026-11-13-334-b-semantic-quality.md)
for the exact checkpoints and pilot evidence. The
[reference-label review handoff](verification/2026-11-13-334-b-label-review.md)
records each case's independent AI review and the remaining human decisions.
