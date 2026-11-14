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
additional concerns separately and distinguishes concerns already detected by
deterministic QA. A fully adjudicated trial containing both a supported
additional concern and an unsupported finding counts once as a clean-trial
false positive.

## Excerpt citation protocol

Reviewer version 2 presents each redacted source as ordered excerpts of at
most 160 characters. It sends each source's text once. The model cites only
excerpt IDs. The host resolves each ID to the source fingerprint and exact
offsets, then applies the existing requirement, cell, documentation, and
reference-count checks. Unknown IDs reject the entire response. Saved evidence
locations keep their existing format. The reviewer remains off by default.

Use the frozen 1.0.1 corpus with version 2 only for offline transport and
admission checks. The historical manifest and calibration remain bound to
version 1. Excerpt metadata counts toward the existing 48,000-character
limit and can change which cases fit. The runner measures the full version 2
request and records any input-limit result before dispatch. The offline 1.0.1
check produced 40 trial rows and 36 mock requests. Both repetitions of the
old near-limit case now exceed the cap (54,867 characters, up from 47,500),
as do both repetitions of the original oversized case. All paired cases
remained eligible.

For the next live comparison, freeze fresh synthetic clean/defect pairs that
were unused during development and separate guardrails for the input limit,
redaction, and insufficient context. Review the labels before seeing any
outputs. Compare both reviewer versions on the same frozen candidates using
their respective pinned runners and identical provider settings. Measure
review coverage, evidence rejection reasons, confirmed holdout recall,
clean-case false positives, and any change in input eligibility. Keep per-arm
results and report differences in eligibility explicitly. Submit the exact
source, corpus, label, prompt, and schema hashes, cases, endpoint, data scope,
and combined call ceiling for separate approval before a provider request.

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
mechanics for the selected implementation and corpus.

The owner-approved November 13 pilot used corpus `1.0.0` on merged revision
`22662cd45b47053a498cb446459e01222ca7e777`. It made 38 requests and returned
valid reviews for 5 of 32 paired trials. The owner supported two of five
admitted findings, including one of 16 eligible paired defect trials and one
additional concern. Twenty evidence-admission failures and 11 invalid
responses have no saved per-check diagnostic. See the
[adjudicated pilot write-up](https://github.com/dhar174/langgraph_system_generator/issues/334#issuecomment-6858902027).

Corpus `1.0.1` updates the rendered workflow schema in two explicit mutant
copies. The four full generator-derived notebooks are all in development.
Holdout and guardrail cases use simplified fixtures. The saved nonblocking
`state_reducer_semantics` and `chatbot_notebook_contract` warnings remain visible
and do not define the focal requirements. The visible prose-only notification
claim in `c-6a4n` may make that case easier than subtler reachability defects.
For `c-3p8w`, apply the owner-approved interpretation: preserve the stated
selected-language requirement in the presence of untrusted instructions, with
no assumption that a specific language was selected. The hard-coded English
response is the deliberate defect when the selected language differs.

The future `run --live` command requires the reviewed plan and its digest.
Changes to the source, dataset, labels, instructions, schema, dependencies,
model, endpoint, caps, repetitions, or retry policy invalidate the plan.
Generate a fresh plan from the exact checkout and environment that would run
the pilot and obtain separate approval. The [offline example plan](verification/334-b-follow-up-example-plan.md) records its tested source revision.
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
also separates preflight reference failures from evidence-admission failures and
shows duplicates, missing-docs behavior, latency sample
counts, and confirmed concerns that deterministic QA missed. Disabled review
has zero semantic findings and zero reviewer calls.

Receipts and journals store a fixed rejection detail when available, with
no rejected response text or validation payloads. The score counts historical
generic rejections whose detail is unavailable. Normal generation artifacts
omit the diagnostic. Receipts also store admitted findings, hashes, provenance,
status, and timing.
Use the versioned fixture to reconstruct the reviewer input for inspection.
Evidence references bind to the redacted text seen by the model. A hash binds
the receipt to evidence and does not certify its authenticity or quality.
The named Luna alias may change over time. Record the requested and reported
model IDs and the run date. A 20-case study is descriptive and cannot justify
general production accuracy, automatic blocking, or an improvement to generated
notebook quality.

See the [follow-up verification](verification/334-b-follow-up.md) and the
[historical offline verification](verification/2026-11-13-334-b-semantic-quality.md)
for exact checkpoints and pilot evidence. The
[reference-label review handoff](verification/2026-11-13-334-b-label-review.md)
records each case's independent AI review and the remaining human decisions.
