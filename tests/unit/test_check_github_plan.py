"""
Unit tests for scripts/check_github_plan.py

All HTTP calls are intercepted via httpx's built-in transport mocking so that
no real network requests are made.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

# ---------------------------------------------------------------------------
# Ensure the scripts/ directory is importable without installing the package
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from check_github_plan import (  # noqa: E402
    PlanReport,
    PlanSignal,
    check_plan,
    main,
    probe_code_scanning,
    probe_copilot_seat,
    probe_dependency_graph,
    probe_marketplace_purchases,
    probe_user_plan,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_response(status_code: int, body: Any) -> httpx.Response:
    """Build a minimal httpx.Response for use in transport mocks."""
    content = json.dumps(body).encode() if body is not None else b""
    return httpx.Response(status_code=status_code, content=content)


class _MockTransport(httpx.BaseTransport):
    """Replay fixed responses keyed by URL path."""

    def __init__(self, routes: dict[str, tuple[int, Any]]) -> None:
        self._routes = routes

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path in self._routes:
            status, body = self._routes[path]
            return _mock_response(status, body)
        return _mock_response(404, {"message": "Not Found"})


def _client(routes: dict[str, tuple[int, Any]]) -> httpx.Client:
    # No base_url: production code constructs full URLs via _GITHUB_API constant.
    return httpx.Client(transport=_MockTransport(routes))


def _patched_client_factory(routes: dict[str, tuple[int, Any]]):
    """Return a drop-in replacement for httpx.Client that uses _MockTransport."""
    original = httpx.Client

    class _PatchedClient(original):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = _MockTransport(routes)
            super().__init__(*args, **kwargs)

    return _PatchedClient


# ---------------------------------------------------------------------------
# PlanSignal / PlanReport unit tests
# ---------------------------------------------------------------------------


def test_plan_signal_defaults():
    sig = PlanSignal(name="x", description="y", endpoint="/x")
    assert sig.strong is False
    assert sig.detected is False
    assert sig.details == ""
    assert sig.error == ""


def test_plan_report_pro_plus_likely_requires_strong_and_detected():
    report = PlanReport()
    weak = PlanSignal(name="w", description="", endpoint="", strong=False, detected=True)
    strong_not_detected = PlanSignal(name="s", description="", endpoint="", strong=True, detected=False)
    report.signals = [weak, strong_not_detected]
    assert report.pro_plus_likely is False

    strong_detected = PlanSignal(name="sd", description="", endpoint="", strong=True, detected=True)
    report.signals.append(strong_detected)
    assert report.pro_plus_likely is True


def test_plan_report_any_signal():
    report = PlanReport()
    assert report.any_signal is False
    report.signals.append(
        PlanSignal(name="x", description="", endpoint="", detected=True)
    )
    assert report.any_signal is True


def test_plan_report_summary_contains_username():
    report = PlanReport(username="octocat", plan_name="pro")
    summary = report.summary()
    assert "octocat" in summary
    assert "pro" in summary


# ---------------------------------------------------------------------------
# probe_user_plan
# ---------------------------------------------------------------------------


def test_probe_user_plan_pro():
    client = _client({"/user": (200, {"login": "octocat", "plan": {"name": "pro"}})})
    username, plan_name, sig = probe_user_plan(client)
    assert username == "octocat"
    assert plan_name == "pro"
    assert sig.detected is True
    assert sig.strong is True
    assert "pro" in sig.details


def test_probe_user_plan_team():
    client = _client({"/user": (200, {"login": "org-member", "plan": {"name": "team"}})})
    _, plan_name, sig = probe_user_plan(client)
    assert plan_name == "team"
    assert sig.detected is True


def test_probe_user_plan_free():
    client = _client({"/user": (200, {"login": "freeuser", "plan": {"name": "free"}})})
    _, plan_name, sig = probe_user_plan(client)
    assert plan_name == "free"
    assert sig.detected is False


def test_probe_user_plan_no_plan_field():
    """Older tokens may not return the plan field."""
    client = _client({"/user": (200, {"login": "someone"})})
    username, plan_name, sig = probe_user_plan(client)
    assert username == "someone"
    assert plan_name == "unknown"
    assert sig.detected is False


def test_probe_user_plan_401():
    client = _client({"/user": (401, {"message": "Bad credentials"})})
    _, _, sig = probe_user_plan(client)
    assert sig.detected is False
    assert "401" in sig.error


# ---------------------------------------------------------------------------
# probe_code_scanning
# ---------------------------------------------------------------------------


def test_probe_code_scanning_active():
    routes = {"/repos/owner/repo/code-scanning/analyses": (200, [{"ref": "main"}, {"ref": "main"}])}
    client = _client(routes)
    sig = probe_code_scanning(client, "owner", "repo")
    assert sig.detected is True
    assert "2" in sig.details


def test_probe_code_scanning_403():
    routes = {"/repos/owner/repo/code-scanning/analyses": (403, {"message": "Forbidden"})}
    client = _client(routes)
    sig = probe_code_scanning(client, "owner", "repo")
    assert sig.detected is False
    assert "403" in sig.error


def test_probe_code_scanning_no_repo():
    client = _client({})
    sig = probe_code_scanning(client, "", "")
    assert sig.detected is False
    assert "skipped" in sig.error.lower()


# ---------------------------------------------------------------------------
# probe_marketplace_purchases
# ---------------------------------------------------------------------------


def test_probe_marketplace_purchases_found():
    body = [{"plan": {"name": "Super Plan"}}, {"plan": {"name": "Other Plan"}}]
    client = _client({"/user/marketplace_purchases": (200, body)})
    sig = probe_marketplace_purchases(client)
    assert sig.detected is True
    assert "2" in sig.details


def test_probe_marketplace_purchases_empty():
    client = _client({"/user/marketplace_purchases": (200, [])})
    sig = probe_marketplace_purchases(client)
    assert sig.detected is False


def test_probe_marketplace_purchases_401():
    client = _client({"/user/marketplace_purchases": (401, {"message": "Requires auth"})})
    sig = probe_marketplace_purchases(client)
    assert sig.detected is False
    assert "401" in sig.error


# ---------------------------------------------------------------------------
# probe_dependency_graph
# ---------------------------------------------------------------------------


def test_probe_dependency_graph_enabled():
    routes = {"/repos/owner/repo/dependency-graph/sbom": (200, {"sbom": {}})}
    client = _client(routes)
    sig = probe_dependency_graph(client, "owner", "repo")
    assert sig.detected is True


def test_probe_dependency_graph_404():
    routes = {"/repos/owner/repo/dependency-graph/sbom": (404, {"message": "Not Found"})}
    client = _client(routes)
    sig = probe_dependency_graph(client, "owner", "repo")
    assert sig.detected is False
    assert "404" in sig.error


def test_probe_dependency_graph_no_repo():
    client = _client({})
    sig = probe_dependency_graph(client, "", "")
    assert "skipped" in sig.error.lower()


# ---------------------------------------------------------------------------
# probe_copilot_seat
# ---------------------------------------------------------------------------


def test_probe_copilot_seat_active():
    routes = {"/orgs/myorg/copilot/billing/seats": (200, {"total_seats": 5})}
    client = _client(routes)
    sig = probe_copilot_seat(client, "myorg")
    assert sig.detected is True
    assert "5" in sig.details


def test_probe_copilot_seat_zero():
    routes = {"/orgs/myorg/copilot/billing/seats": (200, {"total_seats": 0})}
    client = _client(routes)
    sig = probe_copilot_seat(client, "myorg")
    assert sig.detected is False


def test_probe_copilot_seat_no_org():
    client = _client({})
    sig = probe_copilot_seat(client, None)
    assert sig.detected is False
    assert "skipped" in sig.error.lower()


def test_probe_copilot_seat_403():
    routes = {"/orgs/myorg/copilot/billing/seats": (403, {"message": "Forbidden"})}
    client = _client(routes)
    sig = probe_copilot_seat(client, "myorg")
    assert sig.detected is False
    assert "403" in sig.error


# ---------------------------------------------------------------------------
# check_plan (integration of all probes)
# ---------------------------------------------------------------------------


def test_check_plan_all_signals_positive(monkeypatch):
    """check_plan should aggregate all signals and detect pro plan."""
    routes: dict[str, tuple[int, Any]] = {
        "/user": (200, {"login": "prouser", "plan": {"name": "pro"}}),
        "/repos/owner/repo/code-scanning/analyses": (200, [{"ref": "main"}]),
        "/user/marketplace_purchases": (200, [{"plan": {"name": "Extra"}}]),
        "/repos/owner/repo/dependency-graph/sbom": (200, {"sbom": {}}),
        "/orgs/myorg/copilot/billing/seats": (200, {"total_seats": 3}),
    }
    monkeypatch.setattr(httpx, "Client", _patched_client_factory(routes))

    report = check_plan(
        token="fake-token",
        owner="owner",
        repo="repo",
        org="myorg",
    )
    assert report.username == "prouser"
    assert report.plan_name == "pro"
    assert report.pro_plus_likely is True
    assert len(report.signals) == 5


def test_check_plan_free_account(monkeypatch):
    routes: dict[str, tuple[int, Any]] = {
        "/user": (200, {"login": "freeuser", "plan": {"name": "free"}}),
    }
    monkeypatch.setattr(httpx, "Client", _patched_client_factory(routes))

    report = check_plan(token="fake-token")
    assert report.plan_name == "free"
    assert report.pro_plus_likely is False


# ---------------------------------------------------------------------------
# CLI – main()
# ---------------------------------------------------------------------------


def test_main_no_token(capsys, monkeypatch):
    # Ensure GITHUB_TOKEN is absent so the "no token" path is exercised
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    result = main(["--owner", "x", "--repo", "y"])
    captured = capsys.readouterr()
    assert result == 2
    assert "token" in captured.err.lower()


def test_main_json_output(monkeypatch):
    routes: dict[str, tuple[int, Any]] = {
        "/user": (200, {"login": "tester", "plan": {"name": "pro"}}),
    }
    monkeypatch.setattr(httpx, "Client", _patched_client_factory(routes))

    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        result = main(["--token", "fake", "--json"])

    data = json.loads(buf.getvalue())
    assert data["username"] == "tester"
    assert data["plan_name"] == "pro"
    assert data["pro_plus_likely"] is True
    assert isinstance(data["signals"], list)
    assert result == 0


def test_main_text_output(monkeypatch, capsys):
    routes: dict[str, tuple[int, Any]] = {
        "/user": (200, {"login": "tester", "plan": {"name": "free"}}),
    }
    monkeypatch.setattr(httpx, "Client", _patched_client_factory(routes))

    result = main(["--token", "fake"])
    captured = capsys.readouterr()
    assert "tester" in captured.out
    assert result == 1  # free plan → exit 1
