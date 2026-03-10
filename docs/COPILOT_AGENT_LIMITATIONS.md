# GitHub Copilot Agent - Known Tool Limitations

## GitHub API Access

The GitHub tools available to Copilot agents in this repository (and in Copilot Chat generally)
expose only a **limited subset** of GitHub's full API surface. Specifically:

| Capability | Available |
|---|---|
| Read repository contents, files, and directory trees | ✅ |
| Search code, issues, and pull requests | ✅ |
| Read and create issues, comments, and pull requests | ✅ |
| List branches, commits, and tags | ✅ |
| Read GitHub Actions workflow runs and job logs | ✅ |
| **Account billing & subscription status** | ❌ |
| **Copilot Individual / Business / Enterprise plan verification** | ❌ |
| Organization/enterprise billing endpoints | ❌ |

## Why Billing Endpoints Are Unavailable

The GitHub API endpoints for billing, subscription status, and account settings
(e.g., `GET /user/billing/actions_minutes`, `GET /orgs/{org}/settings/billing/actions`,
or any subscription-plan detail endpoint) are **not exposed** through the supported API
surface available to Copilot agents.

This is by design: billing and account-management data require OAuth scopes (such as `read:user`
or private billing scopes) that are **not granted** to the read-only repository-scoped token used
by Copilot's GitHub tools in chat sessions.

As a result, even after a user approves the agent session, the agent cannot independently verify:
- Whether a **GitHub Pro** account tier (or a paid Copilot Individual / Business / Enterprise
  plan) is currently active.
- Billing cycle status, payment method state, or feature entitlements.

## How to Verify Subscription Status

To confirm your GitHub Pro account tier or Copilot subscription plan is active, check directly in the GitHub UI:

1. **Billing & Licensing**: `https://github.com/settings/billing/summary`
2. **Copilot Settings**: `https://github.com/settings/copilot`
3. **Plan & Usage**: `https://github.com/settings/billing/plans`

These pages are the authoritative source; no API call from an agent can substitute for them.
