# Dependency and LangGraph update report

**Date:** 2026-09-11

## Updates applied

- Raised the minimum versions in `requirements.txt` and `setup.py` to the
  current PyPI releases checked on 2026-09-11.
- Updated GitHub Actions workflow references to current release tags.
- Updated deployment workflow action pins to the commit SHAs for the current
  action releases.

The application source was intentionally not changed.

## LangGraph and LangChain findings

- `langgraph` is currently `1.2.11`; its recent release notes describe
  `trace_policy` exposure on `add_node` and checkpoint write-history fixes.
  The repository does not currently need either API change.
- `langchain` is currently `1.4.0` and `langchain-openai` is currently `1.6.2`.
  The existing `ChatOpenAI` construction remains compatible with the documented
  APIs used by this repository.
- `langchain-community` is currently `0.4.2`, but its PyPI project notice says
  the package is being sunset. The repository still imports community FAISS and
  embedding integrations, so a future migration assessment is warranted.
  This report does not change those imports because the issue explicitly
  prohibits application-code updates.

## Follow-up candidates

1. Replace `langchain-community` integrations with their successor packages
   where available, especially vector-store and embedding imports.
2. Add compatibility tests for the updated notebook, FAISS, Chroma, and
   sentence-transformers dependency ranges before publishing a release.
3. Keep the action versions and dependency minimums under Dependabot or an
   equivalent scheduled version audit.

## Sources

- [LangGraph PyPI](https://pypi.org/project/langgraph/)
- [LangChain PyPI](https://pypi.org/project/langchain/)
- [LangChain OpenAI PyPI](https://pypi.org/project/langchain-openai/)
- [LangChain Community PyPI](https://pypi.org/project/langchain-community/)
- [LangGraph release history](https://github.com/langchain-ai/langgraph/releases)
- [LangChain release policy](https://docs.langchain.com/oss/python/release-policy)
