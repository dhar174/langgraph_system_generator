import os
from pathlib import Path

def is_relative_to_base(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


def _compute_base_output() -> Path:
    """
    Compute the base output directory from the ``LNF_OUTPUT_BASE`` environment
    variable, ensuring that it remains within a trusted root directory.

    By default, the trusted root is the current working directory. If the
    configured base path escapes this root, a ValueError is raised.
    """
    root = Path(".").resolve()
    base_env = os.environ.get("LNF_OUTPUT_BASE", ".")

    base_path = Path(base_env)
    if not base_path.is_absolute():
        base_path = (root / base_path).resolve()
    else:
        base_path = base_path.resolve()

    if not is_relative_to_base(base_path, root):
        raise ValueError(
            f"Configured base output directory {base_path} is not under trusted root {root}"
        )

    return base_path


OUTPUT_BASE = _compute_base_output()

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

_BASE_OUTPUT: Path = OUTPUT_BASE

__all__ = [
    "OUTPUT_BASE",
    "_BASE_OUTPUT",
    "OUTPUT_BASE_ENV",
    "DEFAULT_OUTPUT_BASE",
    "is_relative_to_base",
]
