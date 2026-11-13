# #334-B reference-label review handoff

| Review field | Value |
| --- | --- |
| Review date | 2026-11-13 |
| Reviewer | Independent AI reviewer (`/root/independent_eval_plan_review`) |
| Review type | Source-backed AI review; not a human gold standard |
| Disposition | Provisional labels are substantially supported, with the caveats below. Human owner adjudication remains pending. |

## Reviewed artifacts

The review used the model-visible candidate state, generated cell text, supplied fixture documentation, source locations, and actual deterministic QA reports. It did not execute notebook code or make provider calls.

- Dataset: `tests/evaluation/semantic_quality_v1/cases.json` — SHA-256 `f461006e14af06a0a91fa17aa621932750fb3ae98ba4439a7c05fcd89899412d`
- Provisional labels at the independent-review snapshot: `tests/evaluation/semantic_quality_v1/reference_labels.json` — SHA-256 `5b6066a81d4c8bfa9c2be744fffe81665d4b8cc0b5aea31ccc7f0ecead9c00b1`
- Fixture manifest at the independent-review snapshot: `tests/evaluation/semantic_quality_v1/fixture_manifest.json` — SHA-256 `f24dbaeced1f142951671eb2f7204eed215887f836ea8a68a28179ab75161765`

## Label-only follow-up

After the independent review, the corpus author updated only labels and regenerated the manifest. The dataset bytes remain unchanged at SHA-256 `f461006e14af06a0a91fa17aa621932750fb3ae98ba4439a7c05fcd89899412d`.

- Final provisional labels: SHA-256 `26e06ee9a1a5e8ec994b03b06c922c3518ba0b54d92fcd639c6660c5630323b8`
- Refreshed fixture manifest: SHA-256 `f9e309e63cc6e0a9246c18cbf2f8e77bfcf9b0f11fd3e0b30874238873e3791e`

The follow-up changes `label_origin` to state that labels were generated and independently AI-reviewed, with owner/human adjudication pending. It scopes the two generated clean labels (`c-2m7v`, `c-7b9k`) to their paired requirement and adds source-linked `baseline_notes`: the incidental Command-versus-conditional comment mismatch for both, plus the unused calculator `ToolNode` warning outside the support pair's target scope. It does not change candidate cases, paired defect IDs, expected categories, or the AI review dispositions above.

The set has eight complete pairs, with four pairs in development and four in holdout, across customer support, logistics, education, and research coordination. Each pair stays within one split. The four guardrail rows are separate. All 16 paired rows are statically eligible and nonblocking. Runtime QA and notebook execution were not run. The guardrail context sizes are 8,827, 48,120, 10,594, and 47,500 characters; the oversized case should be rejected before dispatch, and the near-limit case is below the 48,000-character cap.

## Per-case adjudication

“Agree” means the stated reference label is supported for the named requirement and candidate evidence. It does not certify all candidate qualities or establish model accuracy.

| Case | Review | Basis |
| --- | --- | --- |
| `c-2m7v` | Agree with scope caveat | The untouched support graph maps billing to billing and technical to technical. Nonblocking QA warnings are listed below; “clean” should mean clean for the paired route requirement, not free of every notebook concern. |
| `c-8r4q` | Agree | The explicit generated copy changes the billing destination to technical, contradicting the named route requirement. The static baseline does not detect this mutation. |
| `c-5w2j` | Agree | The clean operation checks the temperature-sensitive flag and six-hour threshold, then records both manual tracing and human review. |
| `c-0x8d` | Agree | The explicit copy returns only tracking data and omits both the manual trace and human-review actions. |
| `c-7b9k` | Agree with implementation caveat | The generated rubric graph routes to `award_credit` or `instructor_review`, and the respective node instructions express the all-criteria and missing-criteria requirements. This is an LLM-mediated instruction contract, not a deterministic criterion checker; the owner should confirm that this satisfies the intended clean reference. |
| `c-3q6z` | Agree | The explicit graph mutation maps the missing-criteria route to `award_credit` instead of `instructor_review`. The baseline does not detect it. |
| `c-1h5x` | Agree | The offline supervisor pair has independent field-note and archive-review nodes, merges their results, and the final brief maps both results to their source names. |
| `c-4z7f` | Agree | The explicit mutation filters final synthesis to the reviewer result and drops the field-note result required by the prompt. |
| `c-9p3l` | Agree | The clean operation produces a local reminder draft and does not claim to send or contact anyone. |
| `c-6a4n` | Agree | The notebook introduction claims an outbound notification, while the candidate has only a local draft operation and no sending path. This is the intended prose-only capability claim. |
| `c-4m8s` | Agree | The clean operation returns the supplied local window unchanged; the fixture documentation says it is already local wall-clock time. |
| `c-2d9w` | Agree | The explicit copy applies another hour offset, contradicting both the request and the supplied `DeliveryWindow v1` documentation. |
| `c-8t6j` | Agree | The clean operation appends the current feedback and revision summary to prior history. |
| `c-3e9p` | Agree | The explicit copy returns only the current feedback and drops prior history and the revision summary. |
| `c-6g2r` | Agree | The clean operation places field observations in the primary field and secondary summaries in the follow-up field, preserving the requested source distinction. |
| `c-5n8v` | Agree | The explicit copy swaps those sources and therefore reverses the requested evidence priority. |
| `c-0d5h` | Agree | “Help us make a tool for our group” gives no concrete user, goal, or expected behavior; `insufficient_context` is appropriate. |
| `c-7u3m` | Agree | The production context builder reports 48,120 characters, above the 48,000-character input ceiling; it should not be dispatched. |
| `c-3p8w` | Agree with narrow scope note | The candidate accepts `selected_language` but hard-codes English in its output, so it fails for a learner who selected another language. The fixture would be less ambiguous if the prompt named a concrete selection such as Spanish. The embedded override text remains untrusted, and the legitimate trailing requirement is retained after redaction. |
| `c-9a1x` | Agree | The candidate returns the supplied room records unchanged; this preserves the listed room details and local times. The 47,500-character context is below the cap. |

## QA observations to carry into human adjudication

Keep every saved QA report and the current eligibility decisions. These warnings are nonblocking; they must not be rewritten as static passes.

- `c-2m7v` and `c-8r4q` report `state_reducer_semantics`, `tool_reachability`, `chatbot_notebook_contract`, and `domain_architecture_alignment`. The state-reducer warning concerns writers on mutually exclusive router branches, so I do not count it as a supported defect. The chat-loop, persona-gate, and verifier warnings are outside these prompts. The unused calculator `ToolNode` is a real static observation but not a stated capability requirement. The graph-cell comment mentions Command-route destinations while the implementation uses conditional edges; that is a supported, incidental prose/code mismatch already visible to QA. These matters should be distinguished from the paired billing-route mutation.
- `c-7b9k` and `c-3q6z` report `state_reducer_semantics`, `chatbot_notebook_contract`, and `domain_architecture_alignment`. The mutually exclusive route and inapplicable chat-contract observations are not reference defects. The conditional-edge/Command-route comment mismatch is the same incidental baseline concern. The paired rubric branch mutation remains undetected by the deterministic baseline.
- The other paired rows have no failed static QA rules in their saved snapshot. No case is baseline-blocked in this version.

The final labels preserve baseline report IDs and record the incidental warnings above. If a future reviewer reports one of those warnings, retain it for independent annotation; do not guess that it is either a true positive or a false positive from category overlap alone. The unused calculator warning is especially outside the stated support request and needs a human decision on whether it belongs in the semantic-fidelity scope.

## Human handoff and limits

This is independent AI review only. It is not human adjudication, and it does not convert provisional labels into gold labels. Before the labels are treated as resolved scoring references, a human owner should:

1. Confirm the rubric clean-reference caveat for `c-7b9k` and decide whether prompt-mediated model behavior is adequate for the all-criteria requirement.
2. Confirm whether the recorded baseline notes should be adjudicated as additional concerns, especially the Command-versus-conditional comment and unreachable calculator tool.
3. Decide whether to name a specific non-English selected language in `c-3p8w` to make the deliberate hard-coded-English mutation maximally concrete.
4. Add versioned annotations with reviewer identity/type, matched defect ID where supported, verdict, rationale, and annotation version; preserve ambiguity and disagreement rather than resolving it by category overlap.

No live model accuracy was measured. The generated notebook snapshots establish deterministic fake-generation provenance and static QA only. This 20-case study cannot support broad production accuracy, autonomous correctness, or automatic-blocking claims. A separately reviewed and approved live pilot would be needed for live quality evidence.
