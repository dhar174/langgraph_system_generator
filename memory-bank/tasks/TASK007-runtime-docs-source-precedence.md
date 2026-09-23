# TASK007 - Runtime Docs-Source Precedence

**Status:** Complete
**Added:** 2026-09-16
**Updated:** 2026-09-17

## Original Request

Implement executable runtime docs-source precedence for generation context (Issue #375 / PR #377), replacing the direct ArchitectureSelector vector-bypass with provider-neutral retrieval, truthful provenance, and strict offline stub invariants.

## Thought Process

The generator previously bypassed live documentation retrieval in favor of a hardcoded architecture catalog or unverified vector search. A unified, provider-neutral docs retrieval system must:
1. Enforce runtime source precedence: `langchain-docs-local` (primary live) -> `context7` (secondary/cross-check) -> `cached_repo_docs` / `rag_index` (offline fallback).
2. Report truthful provenance in `GenerationContextPack` and manifests: `attempted_sources`, `source_statuses`, `used_sources`, and `fallback_used`.
3. Provide strict `fallback_used` semantics (`True` iff fallback actually contributed at least one final retrieved snippet).
4. Isolate transient stage queries (`ArchitectureSelector`) in `stage_source_statuses` and `consulted_sources` without polluting `used_sources`.
5. Support Model Context Protocol (MCP) streamable HTTP transport (`2026-07-28` protocol version, `_meta` capabilities, and SSE stream handling).
6. Enforce proper transport error boundaries: abort candidate probing immediately on HTTP/network errors instead of sending retry storms.
7. Preserve 100% offline, deterministic stub mode with zero mandatory external package dependencies.

## Implementation Plan

- Implement `DocsSourceProvider`, `DocsSourceRegistry`, and `DocsRetrievalService` in `src/langgraph_system_generator/rag/`.
- Implement `LangChainDocsLocalProvider` querying local MCP/Mintlify tool endpoints with lazy `httpx`.
- Implement `Context7DocsProvider` with two-step workflow (`resolve-library-id` -> `query-docs`) and fallback to `search`.
- Implement `CachedVectorDocsProvider` wrapping `DocsRetriever` off the event loop via `asyncio.to_thread`.
- Build shared `mcp_transport.py` handling JSON-RPC and SSE streams with MCP protocol headers and metadata.
- Wire `rag_retrieval_node` and `ArchitectureSelector` into `DocsRetrievalService`.
- Expose typed `DocsRetrievalFeedback` in `GeneratorState`.
- Write unit test suite in `tests/unit/test_rag_source_precedence.py` covering all provider flows, edge cases, error boundaries, and offline stubs.

## Progress Tracking

**Overall Status:** Complete

### Subtasks

| ID | Description | Status | Updated | Notes |
|----|-------------|--------|---------|-------|
| 7.1 | Provider-neutral RAG service architecture | Complete | 2026-09-16 | `DocsSourceProvider`, `DocsRetrievalService`, `DocsSourceRegistry` established. |
| 7.2 | Live MCP & Context7 providers | Complete | 2026-09-16 | Providers with lazy `httpx` imports and robust payload parsing. |
| 7.3 | MCP streamable HTTP transport helper | Complete | 2026-09-16 | `mcp_transport.py` with protocol `2026-07-28`, headers, and SSE streaming. |
| 7.4 | Transport failure & tool missing boundaries | Complete | 2026-09-17 | Immediate abort on HTTP/network errors; candidate retry only on `-32601` unknown tool. |
| 7.5 | Truthful provenance & stage isolation | Complete | 2026-09-16 | Strict `fallback_used` and `ArchitectureSelector` transient isolation. |
| 7.6 | Unit test suite & offline verification | Complete | 2026-09-17 | Dedicated tests passing 100% offline without live network or external API keys. |
| 7.7 | Registry replacement precedence preservation | Complete | 2026-09-17 | In-place replacement preserving provider index by default; explicit `prepend=True` moves to index 0. |
| 7.8 | Serialized JSON object normalization in LangChain local | Complete | 2026-09-17 | Unpacks serialized JSON `results`/`snippets`/`documents`/`content` collections and single doc objects; preserves `0.0` scores; rejects raw protocol JSON envelopes. |
| 7.9 | Capability-driven stub mode plugin safety | Complete | 2026-09-23 | Explicit `stub_safe: bool = False` capability on `DocsSourceProvider`, `CachedVectorDocsProvider.stub_safe = True`, and capability-driven bypass skipping non-stub-safe providers without probing. |
| 7.10 | Final correctness pass & protocol validation | Complete | 2026-09-23 | Propagated asyncio cancellation in indexer, validated request IDs on HTTP-200 JSON MCP responses, normalized missing custom provider provenance, guarded Context7 against empty snippets with EMPTY fallback, and accepted content/text-only serialized docs with structural protocol rejection. |
| 7.11 | Review follow-up: URL sanitization & protocol rejection | Complete | 2026-09-23 | Redacted URL credentials and query secrets in MCPTransportError messages, and rejected protocol envelopes in Context7 without falling through to raw JSON text emission. |

## Verification & Outcomes

- 66/66 tests pass in `tests/unit/test_rag_source_precedence.py` (13 regression tests added covering HTTP-200 JSON request ID matching/mismatches/notifications, custom provider untagged/explicit provenance, Context7 empty snippet prevention & fallback, LangChain local content/text-only docs, endpoint URL credential sanitization, and Context7 protocol rejection).
- Full unit test suite (748 tests, including dedicated cancellation test in `test_rag.py`), pattern test suite (82 tests), and full pytest suite (866 passed, 3 skipped, 5 warnings) pass cleanly.
- Flake8 reports 0 fatal errors on `src/` and `tests/`, mypy reports 0 issues in `src/langgraph_system_generator/rag/` (13 source files).
- Offline stub mode verified across CLI, API, and package surfaces with deterministic offline generation smoke.
- Preserved prior verified live wire smoke against `https://docs.langchain.com/mcp` (5 snippets, `SUCCESS`).
- ArchitectureSelector live retrieval fan-out / single-flight cache recorded as follow-up item.

