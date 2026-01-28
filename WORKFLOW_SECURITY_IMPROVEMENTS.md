# GitHub Actions Workflow Security Improvements

## Summary

Implemented comprehensive security hardening for GitHub Actions workflows following GitHub Actions security best practices, with focus on:

1. **CodeQL Integration**: Added automated security scanning
2. **Dependency Management**: Jobs that push to main now depend on CodeQL passing
3. **Action Pinning**: Replaced all unpinned actions with specific versions
4. **Least Privilege Permissions**: Implemented granular permission scoping

## Changes Made

### 1. New CodeQL Security Analysis Workflow

**File**: `.github/workflows/codeql.yml` (NEW)

Created comprehensive security scanning workflow with:
- Python static analysis with extended security queries
- Triggers on push, PR, and weekly schedule (Mondays 6 AM UTC)
- Proper permission scoping: `security-events: write`, `actions: read`, `contents: read`
- Reusable workflow design for easy integration

### 2. Updated diagram.yml

**Security Improvements**:
- ✅ Added workflow-level `permissions: contents: read` (least privilege default)
- ✅ Added `codeql` job dependency - diagram only updates after security scan passes
- ✅ **Fixed critical security issue**: Pinned `githubocto/repo-visualizer@main` → `@0.11.0`
- ✅ Scoped permissions: `contents: write` only for diagram update job
- ✅ Added CodeQL workflow reuse

**Before**: Action used unpinned `@main` tag (security risk - could pull malicious updates)
**After**: Action pinned to stable version `@0.11.0`

### 3. Updated wiki-from-code.yml  

**Security Improvements**:
- ✅ Added `codeql` job dependency - wiki generation only runs after security scan passes
- ✅ Moved `pull-requests: write` permission from workflow to job level (least privilege)
- ✅ Added workflow-level default `permissions: contents: read`
- ✅ CodeQL runs conditionally on same events as wiki generation

### 4. Updated wiki-page-creator-action.yml

**Security Improvements**:
- ✅ Added workflow-level `permissions: contents: read`
- ✅ Scoped `contents: write` to job level only
- ✅ **Fixed security issues**:
  - `actions/checkout@master` → `actions/checkout@v4`
  - `docker://decathlon/wiki-page-creator-action:latest` → `:2.0.3`
- ✅ Added descriptive step names

### 5. Updated python-app.yml

**Improvements**:
- ✅ Updated `actions/setup-python@v3` → `@v5` (latest stable)
- ✅ Added pip caching for faster builds: `cache: 'pip'`
- ✅ Added descriptive step name for checkout

### 6. Documentation

**New File**: `docs/CI_CD_WORKFLOWS.md`

Comprehensive documentation covering:
- Workflow purposes and triggers
- Security features and controls
- Permission models
- Workflow dependencies diagram
- Troubleshooting guide
- Best practices and recommendations

## Security Best Practices Implemented

### ✅ Action Pinning
All actions now use specific versions instead of `main`, `master`, or `latest`:
- `@v4`, `@v5` for major version tags
- `@0.11.0` for exact version tags
- `@2.0.3` for Docker images

### ✅ Least Privilege Permissions
- Default: `contents: read` at workflow level
- Elevated permissions granted only at job level when needed
- No workflow has more access than required

### ✅ Security Scanning Integration
- CodeQL runs on all pushes and PRs to main
- Weekly scheduled scans for dependency vulnerabilities
- Jobs that modify repository wait for security scan to pass

### ✅ Workflow Dependencies
```
┌─────────────────┐
│  CodeQL Scan    │  ← Security gate
└────────┬────────┘
         │
         ├─────────────┐
         │             │
         ▼             ▼
┌─────────────┐  ┌──────────────┐
│   Diagram   │  │  Wiki Gen    │  ← Only run if CodeQL passes
└─────────────┘  └──────────────┘
```

## Files Changed

1. `.github/workflows/codeql.yml` - **CREATED**
2. `.github/workflows/diagram.yml` - **MODIFIED**
3. `.github/workflows/wiki-from-code.yml` - **MODIFIED**
4. `.github/workflows/wiki-page-creator-action.yml` - **MODIFIED**
5. `.github/workflows/python-app.yml` - **MODIFIED**
6. `docs/CI_CD_WORKFLOWS.md` - **CREATED**

## Testing

All workflow files validated:
- ✅ YAML syntax validation passed
- ✅ Workflow structure verified
- ✅ Permission scoping confirmed
- ✅ Dependency chain validated

## Next Steps (Recommendations)

1. **Enable Dependabot** for automatic action updates:
   ```yaml
   # .github/dependabot.yml
   version: 2
   updates:
     - package-ecosystem: "github-actions"
       directory: "/"
       schedule:
         interval: "weekly"
   ```

2. **Enable Secret Scanning** with push protection in repository settings

3. **Add SBOM Generation** for releases to improve supply chain transparency

4. **Configure Branch Protection Rules**:
   - Require CodeQL status check before merge
   - Require pull request reviews
   - Enable "Require status checks to pass before merging"

5. **Environment Protection** for sensitive workflows:
   - Already configured for `pypi` environment in python-publish.yml
   - Consider adding for wiki-generation workflows

## Security Checklist Status

- [x] Actions pinned to specific versions
- [x] Permissions: least privilege (default `contents: read`)
- [x] Elevated permissions only at job level
- [x] CodeQL security scanning on push and PR
- [x] Jobs that push to main depend on CodeQL
- [x] OIDC for PyPI publishing (existing)
- [x] Weekly security scans scheduled
- [x] No hardcoded credentials
- [x] Descriptive step names
- [x] Comprehensive documentation

## Additional Security Notes

- **No breaking changes**: All workflows maintain backward compatibility
- **Zero downtime**: Changes are safe to deploy immediately
- **Tested**: All YAML validated before commit
- **Documented**: Comprehensive CI/CD documentation added

## References

- [GitHub Actions Security Best Practices](https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions)
- [CodeQL Documentation](https://codeql.github.com/docs/)
- [OpenID Connect in GitHub Actions](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/about-security-hardening-with-openid-connect)
