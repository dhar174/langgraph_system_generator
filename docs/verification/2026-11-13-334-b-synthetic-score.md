# Semantic reviewer score report

Historical synthetic score generated at `7dbb3ec67728c30a4a58606c475513ed35c08b16` on corpus `1.0.0`.

- Evidence kind: `synthetic-contract`
- Claim scope: `synthetic_contract_evidence_only_live_quality_not_measured`
- Accuracy claim allowed: `false`
- Dataset: `semantic_quality_v1` / `f461006e14af06a0a91fa17aa621932750fb3ae98ba4439a7c05fcd89899412d`
- Reference labels SHA-256: `26e06ee9a1a5e8ec994b03b06c922c3518ba0b54d92fcd639c6660c5630323b8`
- Annotation SHA-256: `none`
- Plan SHA-256: `fca7c1c43eb8583ca8fba2a65895c6e4d53701bf41558fec560958e51c15de76`
- Reviewer prompt SHA-256: `a770f2d6e593cdfbbf8d4bb3aa3e637273626dbfd63c418bc8f0375d918e9ea5`
- Source revision/hash: `7dbb3ec67728c30a4a58606c475513ed35c08b16` / `29efbe0e667df26b7201a489c9611bbe85151cc0d0b502e366f283b0b29fad5d`
- Selected trials: 40; attempts reserved: 38; observed HTTP requests: 38

## Review outcomes

Reviewed with no findings: 0
Reviewed with findings: 36
Valid-review coverage: 32 / 32 (1.000)

### Status counts

| Status | Trials |
| --- | ---: |
| reviewed | 36 |
| skipped | 0 |
| unavailable | 0 |
| invalid_reference | 0 |
| invalid_response | 0 |
| input_limit | 2 |
| output_limit | 0 |
| insufficient_context | 2 |
| cancellation | 0 |
| incomplete | 0 |
| disabled | 0 |

### Reason counts

| Reason | Trials |
| --- | ---: |
| complete | 36 |
| input_limit | 2 |
| insufficient_context | 2 |

## Semantic metrics

Clean false-positive rate on fully adjudicated reviewed trials: 0 / 0 (N/A); unresolved clean trials: 16; with confirmed additional concerns: 0; confirmed lower bound: 0 / 16 eligible clean trials (0.000)
Defect recall: 0 / 16 (0.000); undetected, including abstentions and invalid reviews: 16; unique defects: 0 / 8 (0.000)
Finding precision after independent adjudication: 0 / 0 (N/A); pending/ambiguous: 36
Duplicates after one-to-one matching: 0; unsupported findings: 0
Evidence-admission failures: 0 / 38 (0.000)
Missing-docs cohort: 32 trials; insufficient-context abstentions: 2; admitted docs-conflict findings without docs: 0
Guardrail expected status/reason agreement: 8 / 8 (1.000)
Latency: n=38, mean=30.053 ms, median=16.000 ms, p95=47.000 ms

### Recall by category

| Category | Confirmed / eligible defects | Recall |
| --- | ---: | ---: |
| contradiction | 0 / 6 | 0.000 |
| provided_docs_conflict | 0 / 2 | 0.000 |
| requirements_gap | 0 / 6 | 0.000 |
| unsupported_capability_claim | 0 / 2 | 0.000 |

### Results by split

| Split | Reviewed / selected | Detected / eligible defects | Recall |
| --- | ---: | ---: | ---: |
| development | 16 / 16 | 0 / 8 | 0.000 |
| guardrail | 4 / 8 | 0 / 0 | N/A |
| holdout | 16 / 16 | 0 / 8 | 0.000 |

### Results by repetition

| Repetition | Reviewed / selected | Detected / eligible defects | Recall |
| ---: | ---: | ---: | ---: |
| 1 | 18 / 20 | 0 / 8 | 0.000 |
| 2 | 18 / 20 | 0 / 8 | 0.000 |

## Additional concerns beyond the deterministic baseline

Confirmed additional reference-defect trials: 0
Confirmed redundant findings already detected by the baseline: 0
Additional concern IDs: `None independently confirmed in this run.`

## Limitations

- Advisory review measures detection opinions; it does not repair outputs or establish generated-system correctness.
- Twenty cases are descriptive and do not support broad production-accuracy or automatic-blocking claims.
- Category overlap is a candidate match only; only versioned independent annotations count as confirmed findings.
- Synthetic contract evidence cannot be pooled with live evidence as an accuracy claim.
