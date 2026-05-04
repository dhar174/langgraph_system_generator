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
- Weekly scheduled CodeQL static code analysis

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

**Purpose**: Auto-generates the legacy top-level repository visualization diagram
and opens an update pull request

**Triggers**:
- Push to `main` branch
- Manual workflow dispatch

**Security Controls**:
- **Depends on CodeQL**: Job waits for security scan to pass
- Action pinned to `@0.9.1`, the latest published `githubocto/repo-visualizer`
  tag currently used by the workflow (previously used unpinned `@main`)
- Minimal `GITHUB_TOKEN` permissions: the diagram job keeps `contents: read`
  because branch and pull request writes use the explicit automation token
- Checks `secrets.GH_PAT` before checkout, then uses that token for checkout
  and create-pull-request so automation PRs can trigger normal pull request
  checks under branch protection
- Skips checkout, diagram generation, and PR creation with a workflow notice if
  `secrets.GH_PAT` is not configured, rather than failing the whole workflow

**Workflow**:
1. Run CodeQL security analysis
2. Check whether `secrets.GH_PAT` is configured
3. If the token is available, checkout `main`, generate repo visualization, and
   open or update an `automation/repo-visualization-diagram` pull request with
   `diagram.svg`

`GH_PAT` must be a repository automation token with enough scope to checkout
the repository, push the automation branch, and open/update pull requests. The
default `GITHUB_TOKEN` is not used for this path because PRs created with it do
not trigger the same pull request checks required for protected-branch merging.

The docs-owned Mermaid/DOT/JSON/Figma repository architecture bundle under
`docs/diagrams/repo-architecture-visualizer/` is refreshed locally through the
`repo-architecture-visualizer` skill, not this GitHub Actions workflow.

### GitHub Pages Documentation

**Source**: `docs/` on the `main` branch

**Purpose**: Publishes checked-in project documentation through GitHub Pages

**Publishing Source**:
- Branch: `main`
- Folder: `/docs`
- Site: `https://dhar174.github.io/langgraph_system_generator/`

**Security Controls**:
- Documentation is source-controlled and reviewed through pull requests
- No third-party documentation generation API or long-lived documentation secret
  is required
- The `Documentation` workflow validates required documentation coverage on
  pushes and pull requests

**Workflow**:
1. Update Markdown files under `docs/` or `docs/wiki/`
2. Open a pull request and let the `Documentation` workflow validate coverage
3. Merge to `main`
4. GitHub Pages publishes the updated `/docs` content

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
         ▼
┌─────────────┐
│   Diagram   │
└─────────────┘

┌────────────────────┐
│ Documentation Check │
└─────────┬──────────┘
          │
          ▼
┌────────────────────┐
│  GitHub Pages /docs │
└────────────────────┘
```

The repository documentation site is published from checked-in files under
`docs/`. The `Documentation` workflow validates required documentation coverage
before changes merge, and GitHub Pages serves the merged `/docs` content.

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
