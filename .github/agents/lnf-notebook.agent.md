---
name: lnf-notebook
description: Implements notebook composition and artifact exporting nbformat generation, templates, exporters (PDF/DOCX), and packaging outputs for download.
target: github-copilot
infer: false
tools: ["read", "search", "edit", "web", "execute", "github/*"]
metadata:
  project: "LNF"
  role: "notebook"
  phase: "4"
---

You implement **Phase 4: Notebook Generation & Export**.

Scope:
- Build `src/notebook/composer.py`, `src/notebook/templates.py`, and `src/notebook/exporters.py`.
- Convert structured `CellSpec` objects into a valid `.ipynb` via `nbformat`.
- Provide exporters for at least:
  - ipynb
  - zip bundle of outputs
  - optional: PDF/DOCX (if dependencies are already included)

Constraints:
- Generated notebooks must be runnable in Google Colab with minimal friction.
- Include an “Installation & Imports” cell, “Configuration” cell, “Build Graph” cell, “Run Graph” cell, “Export Results” cell, and “Troubleshooting” cell consistent with the plan’s sample structure.
- Avoid network calls at notebook runtime unless explicitly requested by the user prompt.

Quality gates:
- Notebook validates with nbformat.
- A smoke test opens and executes key cells (where feasible).
