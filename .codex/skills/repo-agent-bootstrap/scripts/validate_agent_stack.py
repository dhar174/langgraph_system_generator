#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
LIB_DIR = SCRIPT_DIR.parent / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

from repo_agent_bootstrap import validate_generated_stack


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a generated repository agent stack.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd(), help="Repository root to validate.")
    args = parser.parse_args()

    report = validate_generated_stack(args.repo_root)
    print(json.dumps(report.to_dict(), indent=2))
    return 0 if report.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
