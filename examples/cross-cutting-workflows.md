# Cross-Cutting Workflows

This page collects text-only examples for the cross-cutting workflows that new
contributors usually need first.

## Testing

**Prompt**

```text
Create a router-based support assistant with a billing path and a technical path.
```

**Command**

```bash
lnf generate "Create a router-based support assistant with a billing path and a technical path." \
  --output ./output/cross-cutting-test \
  --mode stub
```

**Expected output**

- `output/cross-cutting-test/notebook.ipynb`
- `output/cross-cutting-test/manifest.json`
- `manifest.json` reports `mode: "stub"`
- `manifest.json` includes `architecture_type`

If you are editing documentation at the same time, also run:

```bash
python -m pytest tests/unit/test_documentation_coverage.py -q
```

## Logging And Tracing

**Prompt**

```text
Create a research assistant that must log progress and keep execution easy to debug.
```

**Command**

```bash
export LNF_LOG_LEVEL=DEBUG
export LANGSMITH_API_KEY="..."
export LANGSMITH_PROJECT="langgraph-notebook-foundry"
lnf generate "Create a research assistant that must log progress and keep execution easy to debug." \
  --output ./output/cross-cutting-logging \
  --mode live \
  --log-level DEBUG
```

**Expected output**

- verbose CLI logging during generation
- LangSmith traces for live-mode LangChain/LangGraph runs
- `manifest.json` still contains the normal artifact and advisory feedback fields

## Plugin Loading

**Prompt**

```text
Create a notebook that uses an internal custom QA rule and a custom tool registry entry.
```

**Command**

```bash
export TOOLCHAIN_ENGINEER_PLUGIN_MODULES="my_project.plugins.tools"
export QA_REPAIR_PLUGIN_MODULES="my_project.plugins.qa"
lnf generate "Create a notebook that uses an internal custom QA rule and a custom tool registry entry." \
  --output ./output/cross-cutting-plugins \
  --mode stub
```

**Expected output**

- the generator loads the configured plugin modules at startup
- custom registry entries participate without changing CLI flags
- generated artifacts still use the standard manifest and export layout

## Artifact Export

**Prompt**

```text
Create a customer support assistant and export notebook, HTML, Markdown, DOCX, and ZIP artifacts.
```

**Command**

```bash
lnf generate "Create a customer support assistant and export notebook, HTML, Markdown, DOCX, and ZIP artifacts." \
  --output ./output/cross-cutting-export \
  --mode stub \
  --formats ipynb html markdown docx zip
```

**Expected output**

- `notebook.ipynb`
- `notebook.html`
- `notebook.md`
- `notebook.docx`
- `notebook_bundle.zip`
- `manifest.json` with per-format export status

## Related References

- [Developer Onboarding](../docs/wiki/Developer-Onboarding.md)
- [Getting Started](../docs/wiki/Getting-Started.md)
- [Architecture Deep Dive](../docs/wiki/Architecture-Deep-Dive.md)
