# Semantic reviewer pilot plan

Offline example for corpus `1.0.1`. The eligibility fields describe technical preflight. A future live run requires a fresh plan and separate approval.

This is a reviewable plan only. Planning makes zero provider requests.
Synthetic contract responses do not establish live model accuracy.

- Plan SHA-256: `858ca3829e31c16b19d0cc03e74444611ffb52eb81d2f8b31f63a58ba9dc11c2`
- Dataset: `semantic_quality_v1` (20 cases)
- Dataset SHA-256: `b850e5baa6be2a681bf2daa9d99befc5618db347767f62b0a1042ba13250a893`
- Reference labels SHA-256: `1f554b557aaf1edcd9f14980669429f769ad0a28c0f8292f8368ea8b5e69bf1f`
- Source revision: `ef4808b46095b92df0f9535e03fb214e5d2a314b`
- Source SHA-256: `c27e8dcc43b73c1af799fe303b2ca1788b30eefa1664a61b41a3ef26b3c50dfd`
- Reviewer prompt SHA-256: `a770f2d6e593cdfbbf8d4bb3aa3e637273626dbfd63c418bc8f0375d918e9ea5`
- Reviewer version: `1`
- Response schema SHA-256: `7d0aab19ae18e09cebcbcac3575f233ec5fe95ab3fb16ce6a89a3e5527006f90`
- Model: `gpt-6-luna`
- Provider: `openai`
- Endpoint policy: `local`
- Endpoint fingerprint: `d9617135d6fdd0a2cde722d637a1dfcc3da37515708b3ea5d66ae607c8ac785e`
- Output cap: `2048` tokens
- Repetitions: `2`
- Maximum reviewer attempts: `40`
- Maximum eligible attempts for this selection: `38`
- Live-pilot eligible: `true`

## Selected opaque cases

| Slot | Case ID | Split | Domain | Context characters | Planned calls | Eligibility |
|---|---|---|---|---:|---:|---|
| case-01 | `c-0d5h` | guardrail | community_services | 8827 | 2 | eligible |
| case-02 | `c-0x8d` | development | logistics | 10376 | 2 | eligible |
| case-03 | `c-1h5x` | development | research_coordination | 13072 | 2 | eligible |
| case-04 | `c-2d9w` | holdout | logistics | 10722 | 2 | eligible |
| case-05 | `c-2m7v` | development | customer_support | 40465 | 2 | eligible |
| case-06 | `c-3e9p` | holdout | education | 10091 | 2 | eligible |
| case-07 | `c-3p8w` | guardrail | education | 10594 | 2 | eligible |
| case-08 | `c-3q6z` | development | education | 41625 | 2 | eligible |
| case-09 | `c-4m8s` | holdout | logistics | 10636 | 2 | eligible |
| case-10 | `c-4z7f` | development | research_coordination | 13101 | 2 | eligible |
| case-11 | `c-5n8v` | holdout | research_coordination | 10674 | 2 | eligible |
| case-12 | `c-5w2j` | development | logistics | 10534 | 2 | eligible |
| case-13 | `c-6a4n` | holdout | customer_support | 10279 | 2 | eligible |
| case-14 | `c-6g2r` | holdout | research_coordination | 10674 | 2 | eligible |
| case-15 | `c-7b9k` | development | education | 41680 | 2 | eligible |
| case-16 | `c-7u3m` | guardrail | community_services | 48120 | 0 | input_limit |
| case-17 | `c-8r4q` | development | customer_support | 40483 | 2 | eligible |
| case-18 | `c-8t6j` | holdout | education | 10139 | 2 | eligible |
| case-19 | `c-9a1x` | guardrail | community_services | 47500 | 2 | eligible |
| case-20 | `c-9p3l` | holdout | customer_support | 10184 | 2 | eligible |

A future live run requires explicit `--live`, exact digest confirmation, and an unused local claim for this plan. No automatic retry or resume is allowed.
