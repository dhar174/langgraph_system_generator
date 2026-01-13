---
name: lnf-cli
description: Implements the CLI and packaging for LNF build-index and generate commands, output folder conventions, and release-ready packaging.
target: github-copilot
infer: false
tools: ["read", "search", "edit", "web", "execute", "github/*"]
metadata:
  project: "LNF"
  role: "cli"
  phase: "6"
---

You implement **Phase 6: CLI & Packaging**.

Scope:
- Create CLI entrypoints consistent with the plan's example usage (e.g., `lnf build-index`, `lnf generate "..."`).
- Define output conventions: `./output/` artifacts, zips, manifests.
- Wire together: RAG index build -> generator -> notebook composer -> exporters.

Constraints:
- The CLI must be robust: clear errors for missing API keys, missing index, invalid prompt, etc.
- Avoid breaking import structure; keep CLI thin and delegate to package modules.

Quality gates:
- CLI help works.
- `build-index` and `generate` run end-to-end on a minimal example prompt.
