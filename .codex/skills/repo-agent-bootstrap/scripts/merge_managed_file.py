#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
LIB_DIR = SCRIPT_DIR.parent / "lib"
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

from repo_agent_bootstrap import merge_managed_text


def main() -> int:
    parser = argparse.ArgumentParser(description="Replace only the managed section of a target file.")
    parser.add_argument("--target", type=Path, required=True, help="File to update.")
    parser.add_argument("--source-file", type=Path, required=True, help="File containing the new managed content.")
    args = parser.parse_args()

    existing = args.target.read_text(encoding="utf-8") if args.target.exists() else ""
    incoming = args.source_file.read_text(encoding="utf-8")
    merged = merge_managed_text(existing, incoming)
    args.target.parent.mkdir(parents=True, exist_ok=True)
    args.target.write_text(merged, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
