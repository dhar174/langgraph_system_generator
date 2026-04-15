#!/bin/bash

# Session Auto-Commit Hook
# Opt-in hook that commits tracked changes when a Copilot session ends

set -euo pipefail

# Require explicit opt-in
if [[ "${ENABLE_AUTO_COMMIT:-false}" != "true" ]]; then
  echo "⏭️  Auto-commit disabled (set ENABLE_AUTO_COMMIT=true to enable)"
  exit 0
fi

# Check if SKIP_AUTO_COMMIT is set
if [[ "${SKIP_AUTO_COMMIT:-}" == "true" ]]; then
  echo "⏭️  Auto-commit skipped (SKIP_AUTO_COMMIT=true)"
  exit 0
fi

# Check if we're in a git repository
if ! git rev-parse --is-inside-work-tree &>/dev/null; then
  echo "⚠️  Not in a git repository"
  exit 0
fi

# Check for uncommitted changes
if [[ -z "$(git status --porcelain)" ]]; then
  echo "✨ No changes to commit"
  exit 0
fi

echo "📦 Auto-committing tracked changes from Copilot session..."

# Stage tracked changes only
git add -u

# Skip if only untracked files remain
if [[ -z "$(git diff --cached --name-only)" ]]; then
  echo "✨ No tracked changes to commit"
  exit 0
fi

# Create timestamped commit
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
git commit -m "auto-commit: $TIMESTAMP" 2>/dev/null || {
  echo "⚠️  Commit failed"
  exit 0
}

echo "✅ Tracked changes committed locally"

exit 0
