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

from repo_agent_bootstrap import build_repo_profile


def main() -> int:
    parser = argparse.ArgumentParser(description="Inventory a repository for agent-stack bootstrapping.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd(), help="Repository root to inspect.")
    args = parser.parse_args()

    profile = build_repo_profile(args.repo_root)
    print(json.dumps(profile.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
