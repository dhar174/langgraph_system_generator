# GitHub Pro+ Entitlement Verification Guide

> **TL;DR** – there is no single "is Pro+ active?" API endpoint.  
> Use the layered checks below to build a reliable picture from observable signals.

---

## 1  Authoritative UI checks (always start here)

| URL | What to look for |
|-----|-----------------|
| `https://github.com/settings/billing` | Current plan name, billing status, renewal date, payment method |
| `https://github.com/settings/copilot/features` | Shows "GitHub Copilot Individual / Pro+" or an **Upgrade to Pro+** callout |
| `https://github.com/settings/copilot` | Active seat, plan type, included features |

**Interpretation:**

- If the billing page shows an **active paid subscription** and no "payment failed" banner → Pro+ is active.
- If `settings/copilot/features` shows features *included* (not "upgrade required") → Copilot Pro+ entitlements are live.
- An **"Upgrade to Pro+"** button on any settings page → that tier is NOT currently active.

---

## 2  REST API signals

These can be queried programmatically using a personal access token (PAT).

### 2.1  `GET /user` – plan object (strongest signal)

```http
GET https://api.github.com/user
Authorization: Bearer <PAT>
```

Returns a `plan` field for **authenticated** requests:

```json
{
  "login": "yourname",
  "plan": {
    "name": "pro",        // "free" | "pro" | "team" | "enterprise"
    "space": 976562499,
    "private_repos": 9999,
    "collaborators": 0
  }
}
```

`plan.name` is **"pro"** (or "team"/"enterprise") → paid plan is active.  
`plan.name` is **"free"** → no paid personal plan.

> ⚠ The `plan` object is only returned when the token has sufficient user scopes.
> It does **not** distinguish between "GitHub Pro" and "GitHub Pro+" – both return "pro".
> To differentiate Pro from Pro+, check `settings/copilot/features` for the Copilot
> plan label ("Individual" = Copilot Pro, included in GitHub Pro+) or inspect the
> advanced Copilot features that are gated behind Pro+ (e.g. multi-file editing,
> scheduled tasks).  Copilot tier (Individual / Business / Enterprise) requires a
> separate check.

### 2.2  Code Scanning / Advanced Security

```http
GET https://api.github.com/repos/{owner}/{repo}/code-scanning/analyses
```

- **HTTP 200** → GitHub Advanced Security (GHAS) is enabled on this repo → Pro+ / Teams / Enterprise entitlement confirmed.
- **HTTP 404 / 403** → GHAS not enabled (or not on a plan that includes it for private repos).

GHAS is **free for public repos** but requires a **paid plan for private repos**, making it a useful proxy.

### 2.3  Copilot seat (organisation)

```http
GET https://api.github.com/orgs/{org}/copilot/billing/seats
```

- **HTTP 200 with `total_seats > 0`** → Copilot is provisioned for the org → implies paid entitlement.
- Requires `admin:org` permission on the token.

### 2.4  Marketplace purchases

```http
GET https://api.github.com/user/marketplace_purchases
```

Lists active paid Marketplace subscriptions.  Not a direct Pro+ signal, but any active paid subscription implies a billing-capable account.

### 2.5  Dependency Graph / SBOM

```http
GET https://api.github.com/repos/{owner}/{repo}/dependency-graph/sbom
```

- **HTTP 200** → Dependency Graph enabled (a security feature bundled with paid plans for private repos).

---

## 3  Feature-gating proxy checks (low-risk, UI-based)

Try to navigate to features that are **gated behind Pro+** in the GitHub UI:

| Feature | URL | Pro+ signal |
|---------|-----|------------|
| Copilot code review | `Settings → Copilot → Features` | Shown as active, not "upgrade" |
| Multi-file editing | Available in Copilot chat | Usable without upgrade prompt |
| GitHub Advanced Security | `Settings → Code security & analysis` | Shows "enabled" not "upgrade required" |
| Scheduled Copilot tasks | Copilot chat sidebar | No "Pro+ required" banner |
| GitHub Models (free tier included in Pro) | `github.com/marketplace/models` | Accessible |

---

## 4  Automated check script

This repository includes a Python utility that runs the API probes above:

```bash
# Minimal – personal plan check only
python scripts/check_github_plan.py --token "$GITHUB_TOKEN"

# Full check including a repo and org
python scripts/check_github_plan.py \
    --token "$GITHUB_TOKEN" \
    --owner <your-username-or-org> \
    --repo <your-repo-name> \
    --org <your-org>

# Machine-readable JSON output
python scripts/check_github_plan.py --token "$GITHUB_TOKEN" --json
```

Sample output:

```
GitHub plan check for: yourname
  Reported plan name : pro
  Pro+ likely active : YES ✅

Observable signals checked:
  ✅ [strong]  User plan object
               plan.name = 'pro'
  ✅ [strong]  Code Scanning (Advanced Security)
               GHAS active – 3 analysis record(s) found
  ❌ [weak]    Marketplace purchases
               No marketplace purchases found
  ✅ [weak]    Dependency Graph / SBOM
               Dependency graph enabled
  ❌ [strong]  Copilot seat (org)
               No --org provided – skipped
```

---

## 5  Observable signals from this repository's CI

The `.github/workflows/codeql.yml` workflow in this repository runs **GitHub Advanced Security CodeQL** scanning.  When it executes successfully and populates results under the **Security** tab of the repository, that is a reliable indicator that the account has the GHAS entitlement that comes with paid GitHub plans.

You can inspect the last workflow run at:
```
https://github.com/<owner>/<repo>/actions/workflows/codeql.yml
```

---

## 6  What to NOT use as a proxy

| Proxy | Why unreliable |
|-------|---------------|
| Copilot responds in the editor | Free Copilot tier also responds |
| PR / issue creation succeeds | Works on free plans |
| Repo actions run | CI works on free plans (within limits) |
| Number of private repos | Free plan allows limited private repos |

---

## 7  Summary decision tree

```
Does /user return plan.name == "pro"/"team"/"enterprise"?
  YES → strong signal; check billing page to confirm activation date
  NO  → likely free tier; verify at settings/billing

Is Code Scanning active on a private repo?
  YES → GHAS entitlement confirmed → paid plan active
  NO  → insufficient signal alone

Does settings/copilot/features show features "Included"?
  YES → Copilot Pro+ active
  NO (shows "Upgrade") → Copilot Pro+ NOT active
```

---

*For definitive confirmation, always check `https://github.com/settings/billing` directly.*
