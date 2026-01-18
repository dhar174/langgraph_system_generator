"""Global constants for LangGraph System Generator."""

from __future__ import annotations

import os
from pathlib import Path


def _init_base_output() -> Path:
    """Initialize and validate the canonical base output directory.

    The base directory may be configured via the LNF_OUTPUT_BASE environment
    variable, but is always constrained to reside within a trusted root
    directory under the application path. The resulting path is resolved to an
    absolute location and must be a directory (it will be created if missing).
    """
    # Trusted root for all output, anchored to the application directory.
    app_root = Path(__file__).parent.resolve()
    default_root = (app_root / "output").resolve()

    raw_base = os.environ.get("LNF_OUTPUT_BASE")
    if not raw_base:
        base = default_root
    else:
        # Treat LNF_OUTPUT_BASE as a subdirectory under the trusted root and
        # normalize the resulting path before validating containment.
        candidate = (default_root / raw_base).expanduser().resolve()
        try:
            is_relative = candidate.is_relative_to(default_root)  # type: ignore[attr-defined]
        except AttributeError:
            try:
                candidate.relative_to(default_root)
                is_relative = True
            except ValueError:
                is_relative = False

        if not is_relative and candidate != default_root:
            raise RuntimeError(
                "LNF_OUTPUT_BASE must resolve to a directory within the trusted "
                f"output root: {default_root!s}"
            )
        base = candidate

    base.mkdir(parents=True, exist_ok=True)
    return base


_BASE_OUTPUT = _init_base_output()
