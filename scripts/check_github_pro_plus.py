#!/usr/bin/env python3
"""Check whether a GitHub Pro+ subscription is active.

Probes two GitHub REST API endpoints to determine Pro+ activation status:

1. ``GET /user``        — returns plan info (name, private_repos, collaborators).
2. ``GET /user/copilot`` — returns the Copilot seat details for the authenticated
                          user.  This endpoint returns HTTP 200 **only** when the
                          user has an active GitHub Copilot seat, which is bundled
                          with GitHub Pro+.  It returns 404 when Copilot access is
                          absent, making it a reliable Pro+-only probe.

Usage
-----
    # via environment variable (preferred)
    export GITHUB_TOKEN=ghp_...
    python scripts/check_github_pro_plus.py

    # via CLI flag
    python scripts/check_github_pro_plus.py --token ghp_...

    # machine-readable output
    python scripts/check_github_pro_plus.py --json

Exit codes
----------
* 0 — Pro+ confirmed active.
* 1 — Pro+ NOT confirmed (free plan, Copilot absent, or inconclusive).
* 2 — Invocation error (missing token, etc.).
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

GITHUB_API_BASE = "https://api.github.com"

# HTTP status codes returned by the /user/copilot endpoint and their meaning:
#  200 — Copilot seat active  → Pro+ confirmed.
#  404 — No Copilot seat      → Pro+ NOT active.
#  403 — Forbidden / insufficient token scope.
#  422 — Unprocessable Entity → seat present but inactive / pending billing.
_COPILOT_STATUS_MEANINGS = {
    200: "active",
    403: "forbidden",
    404: "no_seat",
    422: "inactive_or_pending",
}


def _api_request(url: str, token: str) -> tuple:
    """Perform a GET request to *url* and return ``(status_code, body_dict)``.

    On success returns ``(200, {...})``.
    On HTTP error returns ``(error_code, {"message": "..."})``.
    On network/parse error returns ``(None, {"error": "..."})``.
    """
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body: dict = {}
        try:
            body = json.loads(exc.read())
        except Exception:
            body = {"message": str(exc)}
        return exc.code, body
    except Exception as exc:
        return None, {"error": str(exc)}


def check_github_plan(token: str) -> dict:
    """Query ``GET /user`` and return a normalised plan dict.

    Returns
    -------
    dict
        ``success`` (bool), ``login`` (str), ``plan`` (dict) on success.
        ``success`` (False), ``status`` (int|None), ``error`` (str) on failure.
    """
    status, body = _api_request(f"{GITHUB_API_BASE}/user", token)
    if status == 200:
        return {
            "success": True,
            "login": body.get("login", ""),
            "plan": body.get("plan", {}),
        }
    return {"success": False, "status": status, "error": body.get("message", str(body))}


def check_copilot_seat(token: str) -> dict:
    """Probe ``GET /user/copilot`` — a Pro+-only endpoint.

    GitHub's Copilot seat endpoint returns HTTP 200 **only** when the
    authenticated user has an active Copilot subscription.  Since Copilot is
    included in GitHub Pro+, a 200 response is a reliable indicator that
    Pro+ is active.

    Returns
    -------
    dict
        ``success`` (bool), ``status`` (int|None), ``data`` / ``message``.
    """
    status, body = _api_request(f"{GITHUB_API_BASE}/user/copilot", token)
    if status == 200:
        return {"success": True, "status": status, "data": body}
    return {
        "success": False,
        "status": status,
        "message": body.get("message", str(body)),
    }


def determine_pro_plus_status(plan_result: dict, copilot_result: dict) -> dict:
    """Synthesise plan + Copilot probe results into a Pro+ status report.

    Parameters
    ----------
    plan_result:
        Output of :func:`check_github_plan`.
    copilot_result:
        Output of :func:`check_copilot_seat`.

    Returns
    -------
    dict with keys:
        ``plan_name``, ``copilot_seat_active`` (bool),
        ``copilot_status_code`` (int|None), ``pro_plus_active`` (bool),
        ``summary`` (str).
    """
    plan_name = ""
    if plan_result.get("success"):
        plan_name = plan_result.get("plan", {}).get("name", "").lower()

    copilot_active: bool = copilot_result.get("success", False)
    copilot_status = copilot_result.get("status")

    # GitHub Pro+ users have a paid plan *and* an active Copilot seat.
    is_paid_plan = plan_name in ("pro", "team", "enterprise")
    pro_plus_active = is_paid_plan and copilot_active

    return {
        "plan_name": plan_name,
        "copilot_seat_active": copilot_active,
        "copilot_status_code": copilot_status,
        "pro_plus_active": pro_plus_active,
        "summary": _build_summary(plan_name, copilot_active, copilot_status),
    }


def _build_summary(plan_name: str, copilot_active: bool, copilot_status) -> str:
    """Return a human-readable one-line summary of Pro+ status."""
    if copilot_active:
        return (
            f"✅ GitHub Pro+ is ACTIVE. "
            f"Plan: '{plan_name}'. "
            f"Copilot seat confirmed active (HTTP {copilot_status})."
        )
    if copilot_status == 422:
        return (
            "⚠️  GitHub Pro+ status UNCERTAIN. "
            f"Plan: '{plan_name}'. "
            "Copilot endpoint returned 422 — subscription may be present but "
            "inactive or pending billing."
        )
    if copilot_status == 404:
        return (
            "❌ GitHub Pro+ does NOT appear to be active. "
            f"Plan: '{plan_name}'. "
            "Copilot seat endpoint returned 404 — no active Copilot subscription."
        )
    if copilot_status == 403:
        return (
            "❌ GitHub Pro+ could not be confirmed. "
            f"Plan: '{plan_name}'. "
            "Copilot seat endpoint returned 403 Forbidden — token may lack "
            "'copilot' scope or user does not have Copilot access."
        )
    return (
        "❓ Unable to determine Pro+ status. "
        f"Plan: '{plan_name}'. "
        f"Copilot check HTTP status: {copilot_status}."
    )


def main(argv=None) -> int:  # noqa: C901
    """Entry point — parse args, run checks, print report.  Returns exit code."""
    parser = argparse.ArgumentParser(
        description=(
            "Check whether GitHub Pro+ subscription is active by probing "
            "the /user and /user/copilot API endpoints."
        )
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("GITHUB_TOKEN", ""),
        help="GitHub personal access token (default: $GITHUB_TOKEN).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output results as JSON instead of human-readable text.",
    )
    args = parser.parse_args(argv)

    if not args.token:
        print(
            "Error: GitHub token required. "
            "Set the GITHUB_TOKEN environment variable or pass --token.",
            file=sys.stderr,
        )
        return 2

    plan_result = check_github_plan(args.token)
    copilot_result = check_copilot_seat(args.token)
    status = determine_pro_plus_status(plan_result, copilot_result)

    if args.json_output:
        print(
            json.dumps(
                {
                    "plan_check": plan_result,
                    "copilot_check": copilot_result,
                    "status": status,
                },
                indent=2,
            )
        )
    else:
        print("\n=== GitHub Pro+ Activation Check ===")
        if plan_result.get("success"):
            print(f"Account : {plan_result.get('login', 'unknown')}")
            print(f"Plan    : {plan_result.get('plan', {}).get('name', 'unknown')}")
        else:
            print(f"Plan check failed: {plan_result.get('error', 'unknown error')}")
        copilot_label = "active" if copilot_result.get("success") else "not active"
        print(f"Copilot : HTTP {copilot_result.get('status')} — {copilot_label}")
        print()
        print(status["summary"])
        print()

    return 0 if status.get("pro_plus_active") else 1


if __name__ == "__main__":
    sys.exit(main())
