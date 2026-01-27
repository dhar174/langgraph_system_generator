import os
from pathlib import Path

_BASE_OUTPUT = Path(os.environ.get("LNF_OUTPUT_BASE", ".")).resolve()

def is_relative_to_base(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False
