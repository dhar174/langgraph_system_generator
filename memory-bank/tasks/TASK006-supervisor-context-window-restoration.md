# TASK006 - Supervisor Context-Window Restoration

**Status:** Complete
**Added:** 2026-09-15
**Updated:** 2026-09-16

## Original Request

Restore bounded supervisor context-window management from PR #229 (Issue #65) adapted to modern LangGraph v1 architecture, resolving review findings and preserving modern Send-based fan-out, credential-free offline tests, and non-lossy hierarchical summarization.

## Thought Process

Older implementations truncated older results or relied on dict insertion order for recency. In multi-specialist runs, supervisor context quickly blows up context limits or silently drops specialist findings.
The solution must:
1. Preserve modern LangGraph v1 contracts (Send-based fan-out, partial state updates).
2. Track specialist recency explicitly via versions so updating an early specialist promotes it to the recent slice.
3. Compute fingerprints from the complete logical older snapshot (`agent:version:sha256`) before any chunking/truncation.
4. Use hierarchical chunked summarization with a bounded reduction tree (`_consolidate_summaries_tree`) and proportional allocation fallback so no intermediate chunk summary is silently dropped.
5. Provide failure-safe LLM summarizer construction and maintain credential-free offline testing.

## Implementation Plan

- Add `task_results_summary: str` and `task_results_summary_fingerprint: str` as supervisor-owned scalar state in `WorkflowState`.
- Add `task_result_versions` with `merge_dicts` reducer; specialist nodes record `max(iterations, max_previous_version + 1)`.
- Implement `_chunk_items` and `_summarize_chunk` to partition older items into bounded chunks (`<= MAX_TOTAL_RESULT_CHARS`).
- Implement `_consolidate_summaries_tree` using bounded reduction rounds (max 3 rounds) with deterministic proportional budget allocation fallback.
- Wrap summarizer client initialization inside `try: ... except Exception:` in `_summarize_older_results` to degrade gracefully to deterministic truncation upon missing credentials or network errors.
- Support `summary_model` override with defaults: standard endpoint uses `gpt-4o-mini`, custom endpoint uses primary model.
- Add unit and pattern integration tests verifying invalidation on changes beyond chunk boundaries, preservation of tail summaries, and credential-free offline execution via `DummyLLM`.

## Progress Tracking

**Overall Status:** Complete

### Subtasks

| ID | Description | Status | Updated | Notes |
|----|-------------|--------|---------|-------|
| 6.1 | Add scalar state & recency tracking | Complete | 2026-09-15 | `task_results_summary`, `task_results_summary_fingerprint`, and `task_result_versions` added. |
| 6.2 | Complete logical snapshot fingerprinting | Complete | 2026-09-15 | Computes stable SHA-256 slice from full `agent:version:sha256` snapshot. |
| 6.3 | Bounded reduction tree consolidation | Complete | 2026-09-15 | Hierarchical chunk summarization with 3-round reduction tree and proportional budget fallback. |
| 6.4 | Safe summarizer initialization | Complete | 2026-09-15 | Constructor failure degrades safely to deterministic truncation. |
| 6.5 | Credential-free tests & verification | Complete | 2026-09-16 | 108 pattern unit tests, 82 pattern integration tests, and 681 unit tests pass; PR #374 merged to main. |

## Verification & Outcomes

- PR #374 merged into `main` (`e78ca58`).
- Proved tail specialist summaries survive multi-chunk consolidation without silent omission.
- Full pattern test suite (82 tests) and unit test suite pass cleanly offline.
