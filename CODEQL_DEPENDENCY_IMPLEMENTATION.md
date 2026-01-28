# CodeQL Dependency Implementation

## How Jobs That Push to Main Now Depend on CodeQL

### Implementation Pattern

Both `diagram.yml` and `wiki-from-code.yml` follow the same pattern:

```yaml
jobs:
  # 1. Run CodeQL as a reusable workflow
  codeql:
    uses: ./.github/workflows/codeql.yml
    permissions:
      contents: read
      security-events: write
      actions: read

  # 2. Main job depends on codeql
  main-job:
    runs-on: ubuntu-latest
    needs: codeql  # ← This creates the dependency
    permissions:
      contents: write  # Only needed for this job
    steps:
      # ... job steps
```

### How It Works

1. **CodeQL runs first** because it has no dependencies
2. **Main job waits** due to `needs: codeql` declaration
3. **If CodeQL fails**, main job is skipped (won't push to main)
4. **If CodeQL passes**, main job proceeds to push changes

### diagram.yml - Before & After

**Before** (❌ No security gate):
```yaml
jobs:
  get_data:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: githubocto/repo-visualizer@main  # ❌ Unpinned!
```

**After** (✅ Security gated):
```yaml
permissions:
  contents: read  # ✅ Least privilege default

jobs:
  codeql:
    uses: ./.github/workflows/codeql.yml  # ✅ Reusable workflow
    permissions:
      contents: read
      security-events: write
      actions: read

  get_data:
    needs: codeql  # ✅ Waits for security scan
    runs-on: ubuntu-latest
    permissions:
      contents: write  # ✅ Scoped to job only
    steps:
      - uses: actions/checkout@v4
      - uses: githubocto/repo-visualizer@0.11.0  # ✅ Pinned!
```

### wiki-from-code.yml - Before & After

**Before** (❌ No security gate):
```yaml
permissions:
  contents: read
  pull-requests: write  # ❌ Too permissive at workflow level

jobs:
  call-adapts-api:
    if: github.event_name == 'push' || ...
    runs-on: ubuntu-latest
    steps:
      # ... wiki generation
```

**After** (✅ Security gated):
```yaml
permissions:
  contents: read  # ✅ Least privilege default

jobs:
  codeql:
    if: github.event_name == 'push' || ...  # ✅ Same conditions
    uses: ./.github/workflows/codeql.yml
    permissions:
      contents: read
      security-events: write
      actions: read

  call-adapts-api:
    if: github.event_name == 'push' || ...
    needs: codeql  # ✅ Waits for security scan
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write  # ✅ Scoped to job only
    steps:
      # ... wiki generation
```

## Execution Flow

### On Push to Main

```
┌────────────────────┐
│  Push to main      │
└─────────┬──────────┘
          │
          ▼
┌────────────────────┐
│  Trigger Workflows │
└─────────┬──────────┘
          │
          ├─────────────────┬────────────────────┐
          │                 │                    │
          ▼                 ▼                    ▼
┌──────────────────┐  ┌──────────────┐  ┌─────────────┐
│  python-app.yml  │  │ diagram.yml  │  │ wiki-from-  │
│  (CI tests)      │  │              │  │ code.yml    │
└──────────────────┘  └──────┬───────┘  └──────┬──────┘
                             │                  │
                             ▼                  ▼
                      ┌────────────────┐  ┌───────────┐
                      │ CodeQL (1st)   │  │ CodeQL    │
                      └────────┬───────┘  │ (1st)     │
                               │          └─────┬─────┘
                      ┌────────▼───────┐        │
                      │ ✓ Security OK  │        │
                      └────────┬───────┘  ┌─────▼──────┐
                               │          │ ✓ Security │
                               ▼          │   OK       │
                      ┌────────────────┐  └─────┬──────┘
                      │ Update diagram │        │
                      │ (push to main) │        ▼
                      └────────────────┘  ┌──────────────┐
                                          │ Generate wiki│
                                          │ (push)       │
                                          └──────────────┘
```

### On CodeQL Failure

```
┌────────────────────┐
│  Push to main      │
└─────────┬──────────┘
          │
          ▼
┌────────────────────┐
│  diagram.yml       │
└─────────┬──────────┘
          │
          ▼
┌────────────────────┐
│  Run CodeQL        │
└─────────┬──────────┘
          │
          ▼
┌────────────────────┐
│  ✗ Security issue  │
│     detected       │
└─────────┬──────────┘
          │
          ▼
┌────────────────────┐
│  ⊘ Diagram job     │
│    SKIPPED         │  ← No push to main happens
└────────────────────┘
```

## Key Benefits

### 1. Security Gate
- No insecure code reaches main
- All commits are scanned before derivative actions

### 2. Fail Fast
- Security issues caught before expensive operations
- No wasted compute on diagram/wiki generation if code is insecure

### 3. Clear Dependency Chain
- Easy to understand: CodeQL → Push jobs
- Simple to maintain and troubleshoot

### 4. Minimal Changes
- Uses reusable workflows (best practice)
- Single source of truth for CodeQL configuration
- Easy to update CodeQL settings in one place

## Reusable Workflow Pattern

The `codeql.yml` is a reusable workflow that can be called from other workflows:

```yaml
# .github/workflows/codeql.yml
name: "CodeQL Security Analysis"
on:
  push:
    branches: [ "main" ]
  pull_request:
    branches: [ "main" ]
  schedule:
    - cron: '0 6 * * 1'
  workflow_call:  # ← Implicit - allows reuse

permissions:
  contents: read

jobs:
  codeql:
    permissions:
      contents: read
      security-events: write
      actions: read
    # ... steps
```

This allows:
1. Standalone execution (push, PR, schedule)
2. Reuse from other workflows (`uses: ./.github/workflows/codeql.yml`)
3. Single source of truth for security scanning

## Testing the Implementation

### Verify Dependency Chain

```bash
# Check workflow files
grep -A 2 "needs:" .github/workflows/diagram.yml
grep -A 2 "needs:" .github/workflows/wiki-from-code.yml

# Expected output:
#   needs: codeql
```

### Validate YAML Syntax

```bash
# Install actionlint (optional but recommended)
brew install actionlint  # macOS
# or download from https://github.com/rhysd/actionlint

# Validate workflows
actionlint .github/workflows/*.yml
```

### Test in Repository

1. Push a test commit to main
2. Check Actions tab - CodeQL should run first
3. Diagram/Wiki jobs should wait for CodeQL
4. On CodeQL failure, dependent jobs should skip

## Security Checklist

- [x] CodeQL workflow created
- [x] diagram.yml depends on CodeQL
- [x] wiki-from-code.yml depends on CodeQL
- [x] All actions pinned to versions
- [x] Least privilege permissions implemented
- [x] Job-level permission scoping
- [x] Reusable workflow pattern used
- [x] Documentation created
- [x] YAML validated

## References

- [GitHub Actions: needs keyword](https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions#jobsjob_idneeds)
- [Reusable Workflows](https://docs.github.com/en/actions/using-workflows/reusing-workflows)
- [CodeQL Analysis](https://docs.github.com/en/code-security/code-scanning/automatically-scanning-your-code-for-vulnerabilities-and-errors/configuring-code-scanning)
