#!/usr/bin/env python3
"""
check_github_plan.py
====================
Probe observable GitHub REST API endpoints to infer whether a personal account
has GitHub Pro+ (or equivalent paid features) active.

Usage
-----
    python scripts/check_github_plan.py --token <GITHUB_PAT>

The personal access token needs at minimum the ``read:user`` scope.
Additional signals require:
  - ``read:org``          – organisation membership & SSO
  - ``copilot``           – Copilot seat status  (if scope exists)

Exit codes
----------
  0  – at least one strong Pro+ signal detected
  1  – no strong signals (free tier or API not accessible)
  2  – unauthenticated / missing token

How it works
------------
GitHub does not expose a single "is Pro+ active?" endpoint, but several API
responses leak plan information that can be used as *observable signals*:

  Signal 1 – ``GET /user`` returns a ``plan`` object containing ``name`` for
             authenticated users.  Values: "free", "pro", "team", "enterprise".

  Signal 2 – ``GET /repos/{owner}/{repo}/code-scanning/analyses`` returns HTTP 200
             with results (not 404 / 403) when GitHub Advanced Security is enabled
             on the repository – a Pro+ / Teams / Enterprise feature.

  Signal 3 – ``GET /copilot/billing/seats`` (org endpoint) or the presence of
             Copilot API access returns 200 when Copilot is provisioned.

  Signal 4 – ``GET /user/marketplace_purchases`` lists active paid GitHub
             Marketplace subscriptions.

  Signal 5 – ``GET /repos/{owner}/{repo}/dependency-graph/sbom`` returns an SBOM
             when the Dependency Graph (a security feature) is enabled.

For a definitive answer always check:
  https://github.com/settings/billing  (authoritative)
  https://github.com/settings/copilot/features
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

_GITHUB_API = "https://api.github.com"
_ACCEPT = "application/vnd.github+json"
_API_VERSION = "2022-11-28"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class PlanSignal:
    """A single observable entitlement signal and its result."""

    name: str
    description: str
    endpoint: str
    strong: bool = False  # True ⟹ direct plan evidence
    detected: bool = False
    details: str = ""
    error: str = ""


@dataclass
class PlanReport:
    """Aggregated results of all signals."""

    username: str = ""
    plan_name: str = "unknown"
    signals: list[PlanSignal] = field(default_factory=list)

    @property
    def pro_plus_likely(self) -> bool:
        return any(s.strong and s.detected for s in self.signals)

    @property
    def any_signal(self) -> bool:
        return any(s.detected for s in self.signals)

    def summary(self) -> str:
        lines: list[str] = [
            f"GitHub plan check for: {self.username or '(unknown)'}",
            f"  Reported plan name : {self.plan_name}",
            f"  Pro+ likely active : {'YES ✅' if self.pro_plus_likely else 'NO / uncertain ❌'}",
            "",
            "Observable signals checked:",
        ]
        for sig in self.signals:
            icon = "✅" if sig.detected else "❌"
            strength = "[strong]" if sig.strong else "[weak] "
            lines.append(f"  {icon} {strength} {sig.name}")
            if sig.details:
                lines.append(f"           {sig.details}")
            if sig.error:
                lines.append(f"           ⚠ {sig.error}")
        lines.extend([
            "",
            "Authoritative verification:",
            "  https://github.com/settings/billing",
            "  https://github.com/settings/copilot/features",
        ])
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": _ACCEPT,
        "X-GitHub-Api-Version": _API_VERSION,
    }


def _get(client: httpx.Client, path: str) -> tuple[int, Any]:
    """Issue a GET request; return (status_code, parsed_body_or_None)."""
    try:
        resp = client.get(f"{_GITHUB_API}{path}")
        try:
            body = resp.json()
        except Exception:
            body = None
        return resp.status_code, body
    except httpx.RequestError as exc:
        return -1, {"error": str(exc)}


# ---------------------------------------------------------------------------
# Individual signal probes
# ---------------------------------------------------------------------------


def probe_user_plan(client: httpx.Client) -> tuple[str, str, PlanSignal]:
    """Signal 1: /user plan object."""
    signal = PlanSignal(
        name="User plan object",
        description="GET /user – 'plan.name' field",
        endpoint="/user",
        strong=True,
    )
    status, body = _get(client, "/user")
    username = ""
    plan_name = "unknown"

    if status == 200 and isinstance(body, dict):
        username = body.get("login", "")
        plan_obj = body.get("plan") or {}
        plan_name = plan_obj.get("name", "unknown")
        if plan_name in {"pro", "team", "enterprise"}:
            signal.detected = True
            signal.details = f"plan.name = '{plan_name}'"
        elif plan_name == "free":
            signal.detected = False
            signal.details = "plan.name = 'free' – no paid plan detected"
        else:
            signal.details = f"plan.name = '{plan_name}' (unexpected value)"
    elif status == 401:
        signal.error = "HTTP 401 – token invalid or missing required scope"
    else:
        signal.error = f"HTTP {status}"

    return username, plan_name, signal


def probe_code_scanning(
    client: httpx.Client, owner: str, repo: str
) -> PlanSignal:
    """Signal 2: Code Scanning / Advanced Security."""
    signal = PlanSignal(
        name="Code Scanning (Advanced Security)",
        description=f"GET /repos/{owner}/{repo}/code-scanning/analyses",
        endpoint=f"/repos/{owner}/{repo}/code-scanning/analyses",
        strong=True,
    )
    if not (owner and repo):
        signal.error = "No repo provided – skipped"
        return signal

    status, body = _get(client, f"/repos/{owner}/{repo}/code-scanning/analyses")
    if status == 200:
        count = len(body) if isinstance(body, list) else 0
        signal.detected = True
        signal.details = f"GHAS active – {count} analysis record(s) found"
    elif status == 403:
        signal.error = "HTTP 403 – Advanced Security not enabled or insufficient permissions"
    elif status == 404:
        signal.error = "HTTP 404 – repo not found or feature not enabled"
    else:
        signal.error = f"HTTP {status}"
    return signal


def probe_marketplace_purchases(client: httpx.Client) -> PlanSignal:
    """Signal 3: Marketplace purchases."""
    signal = PlanSignal(
        name="Marketplace purchases",
        description="GET /user/marketplace_purchases",
        endpoint="/user/marketplace_purchases",
        strong=False,
    )
    status, body = _get(client, "/user/marketplace_purchases")
    if status == 200 and isinstance(body, list):
        if body:
            signal.detected = True
            plans = [p.get("plan", {}).get("name", "?") for p in body]
            signal.details = f"{len(body)} purchase(s): {', '.join(plans)}"
        else:
            signal.details = "No marketplace purchases found"
    elif status == 401:
        signal.error = "HTTP 401 – token requires 'user' scope"
    else:
        signal.error = f"HTTP {status}"
    return signal


def probe_dependency_graph(
    client: httpx.Client, owner: str, repo: str
) -> PlanSignal:
    """Signal 4: Dependency Graph SBOM (security feature)."""
    signal = PlanSignal(
        name="Dependency Graph / SBOM",
        description=f"GET /repos/{owner}/{repo}/dependency-graph/sbom",
        endpoint=f"/repos/{owner}/{repo}/dependency-graph/sbom",
        strong=False,
    )
    if not (owner and repo):
        signal.error = "No repo provided – skipped"
        return signal

    status, body = _get(client, f"/repos/{owner}/{repo}/dependency-graph/sbom")
    if status == 200:
        signal.detected = True
        signal.details = "Dependency graph enabled"
    elif status == 404:
        signal.error = "HTTP 404 – dependency graph not enabled"
    else:
        signal.error = f"HTTP {status}"
    return signal


def probe_copilot_seat(client: httpx.Client, org: Optional[str]) -> PlanSignal:
    """Signal 5: Copilot seat via org endpoint (if org provided)."""
    signal = PlanSignal(
        name="Copilot seat (org)",
        description=f"GET /orgs/{org}/copilot/billing/seats" if org else "skipped – no org",
        endpoint=f"/orgs/{org}/copilot/billing/seats" if org else "",
        strong=True,
    )
    if not org:
        signal.error = "No --org provided – skipped"
        return signal

    status, body = _get(client, f"/orgs/{org}/copilot/billing/seats")
    if status == 200 and isinstance(body, dict):
        total = body.get("total_seats", 0)
        signal.detected = total > 0
        signal.details = f"{total} Copilot seat(s) allocated in org '{org}'"
    elif status == 403:
        signal.error = "HTTP 403 – requires admin:org permission or Copilot not provisioned"
    elif status == 404:
        signal.error = "HTTP 404 – org not found or Copilot not provisioned"
    else:
        signal.error = f"HTTP {status}"
    return signal


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def check_plan(
    token: str,
    owner: str = "",
    repo: str = "",
    org: Optional[str] = None,
    timeout: float = 10.0,
) -> PlanReport:
    """Run all probes and return a :class:`PlanReport`."""
    report = PlanReport()
    with httpx.Client(headers=_headers(token), timeout=timeout) as client:
        username, plan_name, sig1 = probe_user_plan(client)
        report.username = username
        report.plan_name = plan_name
        report.signals.append(sig1)

        report.signals.append(probe_code_scanning(client, owner, repo))
        report.signals.append(probe_marketplace_purchases(client))
        report.signals.append(probe_dependency_graph(client, owner, repo))
        report.signals.append(probe_copilot_seat(client, org))

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Probe GitHub API to infer Pro+ plan activation.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--token",
        default=os.getenv("GITHUB_TOKEN", ""),
        help="Personal access token (or set GITHUB_TOKEN env var)",
    )
    parser.add_argument(
        "--owner",
        default="",
        help="Repository owner for repo-level signals (e.g. 'octocat')",
    )
    parser.add_argument(
        "--repo",
        default="",
        help="Repository name for repo-level signals (e.g. 'hello-world')",
    )
    parser.add_argument(
        "--org",
        default=None,
        help="Organisation name for Copilot seat check",
    )
    parser.add_argument(
        "--json",
        dest="output_json",
        action="store_true",
        help="Emit machine-readable JSON instead of human-readable text",
    )
    args = parser.parse_args(argv)

    if not args.token:
        print(
            "ERROR: no GitHub token provided.  "
            "Pass --token or set the GITHUB_TOKEN environment variable.",
            file=sys.stderr,
        )
        return 2

    report = check_plan(
        token=args.token,
        owner=args.owner,
        repo=args.repo,
        org=args.org,
    )

    if args.output_json:
        data = {
            "username": report.username,
            "plan_name": report.plan_name,
            "pro_plus_likely": report.pro_plus_likely,
            "signals": [
                {
                    "name": s.name,
                    "strong": s.strong,
                    "detected": s.detected,
                    "details": s.details,
                    "error": s.error,
                }
                for s in report.signals
            ],
        }
        print(json.dumps(data, indent=2))
    else:
        print(report.summary())

    return 0 if report.pro_plus_likely else 1


if __name__ == "__main__":
    sys.exit(main())
