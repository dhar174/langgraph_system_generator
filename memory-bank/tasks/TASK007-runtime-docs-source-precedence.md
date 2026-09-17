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
| 7.6 | Unit test suite & offline verification | Complete | 2026-09-17 | 36 unit tests passing 100% offline without live network or external API keys. |

## Verification & Outcomes

- 36/36 tests pass in `tests/unit/test_rag_source_precedence.py`.
- Full unit test suite (717 tests) and pattern test suite (82 tests) pass cleanly.
- Flake8 reports 0 fatal errors, mypy reports 0 issues in `src/langgraph_system_generator/rag/`.
- Offline stub mode verified across CLI, API, and package surfaces.
- Live MCP wire smoke validation against `https://docs.langchain.com/mcp` succeeded with 5 snippets and `DocsSourceStatus.SUCCESS`.
- Pushed commit `eb40bd4` to branch `fix/375-runtime-docs-source-precedence` and updated PR #377.

