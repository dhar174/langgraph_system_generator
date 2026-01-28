# CI/CD Workflows

This document describes the GitHub Actions workflows configured for this repository.

## Security-First Approach

All workflows follow security best practices:

- **Least Privilege Permissions**: Default to `contents: read` at workflow level
- **Action Pinning**: All actions pinned to specific versions (e.g., `@v4`, `@v5`)
- **Permission Scoping**: Elevated permissions granted only at job level when needed
- **CodeQL Integration**: Security scanning runs on all pushes and pull requests

## Workflows

### CodeQL Security Analysis

**File**: `.github/workflows/codeql.yml`

**Purpose**: Automated security scanning for Python code

**Triggers**:
- Push to `main` branch
- Pull requests to `main` branch  
- Weekly schedule (Mondays at 6 AM UTC)

**Security Features**:
- Static Application Security Testing (SAST)
- Extended security queries
- Security and quality analysis
- Weekly scheduled scans for dependency vulnerabilities

**Permissions**:
- `contents: read` - Repository checkout
- `security-events: write` - Upload findings to Security tab
- `actions: read` - Query workflow metadata

### Python Application Build & Test

**File**: `.github/workflows/python-app.yml`

**Purpose**: CI validation with linting and testing

**Triggers**:
- Push to `main` branch
- Pull requests to `main` branch

**Features**:
- Python 3.10 with pip caching
- Flake8 linting
- Pytest test execution

**Permissions**:
- `contents: read` (default)

### Create Diagram

**File**: `.github/workflows/diagram.yml`

**Purpose**: Auto-generates and commits repository visualization diagram

**Triggers**:
- Push to `main` branch
- Manual workflow dispatch

**Security Controls**:
- **Depends on CodeQL**: Job waits for security scan to pass
- Action pinned to `@0.11.0` (previously used unpinned `@main`)
- Minimal permissions: `contents: write` only for diagram job

**Workflow**:
1. Run CodeQL security analysis
2. Generate repo visualization (only if CodeQL passes)
3. Commit diagram to repository

### Generate Wiki from Code

**File**: `.github/workflows/wiki-from-code.yml`

**Purpose**: Auto-generates wiki documentation from code on push to main

**Triggers**:
- Push to `main` branch
- Closed pull requests to `main` (only if merged)

**Security Controls**:
- **Depends on CodeQL**: Job waits for security scan to pass
- Scoped permissions for API calls
- Uses OIDC-style authentication where possible

**Workflow**:
1. Run CodeQL security analysis (only on relevant events)
2. Call documentation API (only if CodeQL passes)
3. Generate wiki pages

### Python Package Publishing

**File**: `.github/workflows/python-publish.yml`

**Purpose**: Publishes Python package to PyPI on release

**Triggers**:
- Release published

**Security Features**:
- **OIDC Trusted Publishing**: No long-lived credentials
- Separate build and publish jobs
- Environment protection for `pypi` environment
- `id-token: write` for OIDC authentication

**Permissions**:
- Build job: `contents: read`
- Publish job: `id-token: write` (for OIDC)

### Milestone Closure

**File**: `.github/workflows/wiki-page-creator-action.yml`

**Purpose**: Creates release notes and wiki pages when milestones close

**Triggers**:
- Milestone closed

**Security Updates**:
- Actions pinned to specific versions
- `checkout@v4` (previously `@master`)
- Docker images pinned to tags (previously `latest`)
- Scoped permissions added

## Dependency Management

### Dependabot (Recommended)

To keep actions up to date, consider adding `.github/dependabot.yml`:

```yaml
version: 2
updates:
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 10
```

## Security Checklist

- [x] Actions pinned to specific versions
- [x] Permissions: least privilege (default `contents: read`)
- [x] Elevated permissions only at job level
- [x] CodeQL security scanning on push and PR
- [x] Jobs that push to main depend on CodeQL
- [x] OIDC for PyPI publishing (no long-lived tokens)
- [x] Weekly security scans scheduled
- [x] No hardcoded credentials
- [ ] Consider enabling secret scanning with push protection
- [ ] Consider adding Dependabot for action updates
- [ ] Consider adding SBOM generation for releases

## Workflow Dependencies

```
┌─────────────────┐
│  CodeQL Scan    │
└────────┬────────┘
         │
         ├─────────────┐
         │             │
         ▼             ▼
┌─────────────┐  ┌──────────────┐
│   Diagram   │  │  Wiki Gen    │
└─────────────┘  └──────────────┘
```

Jobs that modify the `main` branch (`diagram.yml`, `wiki-from-code.yml`) now depend on the CodeQL security scan passing. This ensures no code with security issues is committed.

## Local Testing

To validate workflow syntax locally:

```bash
# Install actionlint
brew install actionlint  # macOS
# or download from https://github.com/rhysd/actionlint

# Validate all workflows
actionlint .github/workflows/*.yml
```

## Troubleshooting

### CodeQL Failures

If CodeQL fails, check:
1. Security tab for specific findings
2. CodeQL analysis logs in Actions tab
3. Fix identified issues before merge

### Workflow Permission Errors

If you see permission errors:
1. Check job-level `permissions` in workflow file
2. Verify required permissions are granted
3. Ensure repository settings allow workflows to create/update content

### Action Version Updates

To update action versions:
1. Check action repository for latest release
2. Update `@vX` reference in workflow
3. Review action changelog for breaking changes
4. Test in a separate branch first

## Additional Resources

- [GitHub Actions Security Hardening](https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions)
- [OpenID Connect in GitHub Actions](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/about-security-hardening-with-openid-connect)
- [CodeQL Documentation](https://codeql.github.com/docs/)
