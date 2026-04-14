---
name: 'Session Auto-Commit'
description: 'Opt-in hook that commits tracked changes locally when a Copilot coding agent session ends'
tags: ['automation', 'git', 'productivity']
---

# Session Auto-Commit Hook

Provides an opt-in local commit hook for GitHub Copilot coding agent sessions, so tracked changes can be saved without automatically pushing or sweeping up untracked files.

## Overview

When explicitly enabled, this hook runs at the end of each Copilot coding agent session and automatically:
- Detects if there are uncommitted changes
- Stages tracked changes only
- Creates a timestamped commit

## Features

- **Opt-In Safety**: Disabled by default unless explicitly enabled
- **Local Backup**: Saves tracked work from a Copilot session in a local commit
- **Timestamped Commits**: Each auto-commit includes the session end time
- **Safer Staging**: Leaves untracked files alone
- **Safe Execution**: Only commits when there are staged tracked changes

## Installation

1. Copy this hook folder to your repository's `.github/hooks/` directory:
   ```bash
   cp -r hooks/session-auto-commit .github/hooks/
   ```

2. Ensure the script is executable:
   ```bash
   chmod +x .github/hooks/session-auto-commit/auto-commit.sh
   ```

3. Enable it explicitly in the shell where you want it to run:
   ```bash
   export ENABLE_AUTO_COMMIT=true
   ```

4. Commit the hook configuration to your repository's default branch

## Configuration

The hook is configured in `hooks.json` to run on the `sessionEnd` event, but the script exits immediately unless `ENABLE_AUTO_COMMIT=true` is set:

```json
{
  "version": 1,
  "hooks": {
    "sessionEnd": [
      {
        "type": "command",
        "bash": ".github/hooks/session-auto-commit/auto-commit.sh",
        "timeoutSec": 30
      }
    ]
  }
}
```

## How It Works

1. When a Copilot coding agent session ends, the hook executes
2. Checks if inside a Git repository
3. Detects uncommitted changes using `git status`
4. Stages tracked changes with `git add -u`
5. Creates a commit with format: `auto-commit: YYYY-MM-DD HH:MM:SS`
6. Reports local commit success or failure

## Customization

You can customize the hook by modifying `auto-commit.sh`:

- **Commit Message Format**: Change the timestamp format or message prefix
- **Selective Staging**: Use a narrower `git add` pattern instead of `-u`
- **Notifications**: Add desktop notifications or Slack messages

## Disabling

To disable or bypass auto-commits:

1. Leave `ENABLE_AUTO_COMMIT` unset (default behavior)
2. Or temporarily bypass an enabled hook with: `export SKIP_AUTO_COMMIT=true`

## Notes

- The hook respects local commit hooks because it does not use `--no-verify`
- The hook does not push automatically
- Works with both Copilot coding agent and GitHub Copilot CLI
