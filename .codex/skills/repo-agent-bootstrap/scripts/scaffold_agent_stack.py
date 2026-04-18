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

from repo_agent_bootstrap import (
    ExternalSource,
    build_bootstrap_files,
    build_repo_profile,
    write_bootstrap_files,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Scaffold a managed repository agent stack.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd(), help="Repository root to scaffold.")
    parser.add_argument("--generated-on", required=True, help="Stable date string recorded in generated files.")
    parser.add_argument(
        "--external-sources-file",
        type=Path,
        help="Optional JSON file containing pinned external sources to record in provenance.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print the planned file list instead of writing.")
    args = parser.parse_args()

    external_sources = _load_external_sources(args.external_sources_file)
    profile = build_repo_profile(args.repo_root)
    rendered = build_bootstrap_files(
        profile,
        generated_on=args.generated_on,
        external_sources=external_sources,
    )

    if args.dry_run:
        print(json.dumps({"profile": profile.to_dict(), "files": sorted(rendered)}, indent=2))
        return 0

    written = write_bootstrap_files(args.repo_root, rendered)
    print(json.dumps({"written": written}, indent=2))
    return 0


def _load_external_sources(path: Path | None) -> list[ExternalSource]:
    if not path:
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [ExternalSource(**item) for item in payload]


if __name__ == "__main__":
    raise SystemExit(main())
