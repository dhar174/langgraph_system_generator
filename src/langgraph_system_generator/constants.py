import os
from pathlib import Path

_BASE_OUTPUT = Path(os.environ.get("LNF_OUTPUT_BASE", ".")).resolve()

def is_relative_to_base(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False

def resolve_under_base(path: Path) -> Path:
    """
    Resolve a path intended to be under the configured base output directory.

    The returned path is normalized and verified to be contained within
    ``_BASE_OUTPUT``. A ValueError is raised if the check fails.
    """
    full_path = (_BASE_OUTPUT / path).resolve()
    if not is_relative_to_base(full_path, _BASE_OUTPUT):
        raise ValueError(f"path {full_path} is not under base output {_BASE_OUTPUT}")
    return full_path
