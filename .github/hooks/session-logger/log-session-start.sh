#!/bin/bash

# Log session start event

set -euo pipefail

# Skip if logging disabled
if [[ "${SKIP_LOGGING:-}" == "true" ]]; then
  exit 0
fi

# Read input from Copilot
INPUT=$(cat)

# Create logs directory if it doesn't exist
mkdir -p logs/copilot

# Extract timestamp and session info
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
CWD=$(pwd)

# Log session start (prefer jq for JSON encoding; fall back safely if unavailable)
if command -v jq &>/dev/null; then
  jq -Rn --arg timestamp "$TIMESTAMP" --arg cwd "$CWD" '{"timestamp":$timestamp,"event":"sessionStart","cwd":$cwd}' >> logs/copilot/session.log
elif command -v python3 &>/dev/null; then
  python3 - "$TIMESTAMP" "$CWD" >> logs/copilot/session.log <<'PY'
import json
import sys

timestamp, cwd = sys.argv[1], sys.argv[2]
print(json.dumps({"timestamp": timestamp, "event": "sessionStart", "cwd": cwd}))
PY
else
  echo "⚠️  Session logging skipped (missing jq and python3)"
  exit 0
fi

echo "📝 Session logged"
exit 0
