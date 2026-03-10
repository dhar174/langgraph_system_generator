"""Unit tests for scripts/check_github_pro_plus.py.

All HTTP calls are mocked so no real network access or GitHub token is
required when running the test suite.
"""

import io
import json
import os
import sys
import unittest
import urllib.error
from contextlib import redirect_stdout
from io import BytesIO
from unittest.mock import MagicMock, patch

# Make the scripts directory importable.
_SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
sys.path.insert(0, os.path.abspath(_SCRIPTS_DIR))

from check_github_pro_plus import (  # noqa: E402
    _build_summary,
    check_copilot_seat,
    check_github_plan,
    determine_pro_plus_status,
    main,
)

# Keys that :func:`determine_pro_plus_status` must always return.
EXPECTED_STATUS_KEYS = (
    "plan_name",
    "copilot_seat_active",
    "copilot_status_code",
    "pro_plus_active",
    "summary",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(data: dict, status: int = 200):
    """Return a context-manager-compatible mock for urllib.request.urlopen."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(data).encode()
    mock_resp.status = status
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


def _mock_http_error(code: int, message: str = "error"):
    """Return an HTTPError whose fp.read() yields a JSON body."""
    fp = BytesIO(json.dumps({"message": message}).encode())
    return urllib.error.HTTPError(
        url="https://api.github.com/test",
        code=code,
        msg=message,
        hdrs=None,
        fp=fp,
    )


# ---------------------------------------------------------------------------
# check_github_plan
# ---------------------------------------------------------------------------

class TestCheckGitHubPlan(unittest.TestCase):
    """Tests for :func:`check_github_plan`."""

    @patch("urllib.request.urlopen")
    def test_success_returns_login_and_plan(self, mock_open):
        mock_open.return_value = _mock_response(
            {
                "login": "octocat",
                "plan": {"name": "pro", "space": 976562499, "private_repos": 9999},
            }
        )
        result = check_github_plan("fake_token")

        self.assertTrue(result["success"])
        self.assertEqual(result["login"], "octocat")
        self.assertEqual(result["plan"]["name"], "pro")

    @patch("urllib.request.urlopen")
    def test_free_plan_returned(self, mock_open):
        mock_open.return_value = _mock_response(
            {"login": "freeuser", "plan": {"name": "free"}}
        )
        result = check_github_plan("fake_token")

        self.assertTrue(result["success"])
        self.assertEqual(result["plan"]["name"], "free")

    @patch("urllib.request.urlopen")
    def test_missing_plan_key_returns_empty_dict(self, mock_open):
        # Some GitHub API responses omit the plan key for certain auth contexts.
        mock_open.return_value = _mock_response({"login": "noplanner"})
        result = check_github_plan("fake_token")

        self.assertTrue(result["success"])
        self.assertEqual(result["plan"], {})

    @patch("urllib.request.urlopen")
    def test_401_returns_failure(self, mock_open):
        mock_open.side_effect = _mock_http_error(401, "Bad credentials")
        result = check_github_plan("bad_token")

        self.assertFalse(result["success"])
        self.assertEqual(result["status"], 401)

    @patch("urllib.request.urlopen")
    def test_network_error_returns_failure(self, mock_open):
        mock_open.side_effect = OSError("connection refused")
        result = check_github_plan("any_token")

        self.assertFalse(result["success"])
        self.assertIsNone(result["status"])


# ---------------------------------------------------------------------------
# check_copilot_seat
# ---------------------------------------------------------------------------

class TestCheckCopilotSeat(unittest.TestCase):
    """Tests for :func:`check_copilot_seat`.

    The ``GET /user/copilot`` endpoint is the Pro+-only probe: it returns 200
    only when the authenticated user has an active Copilot seat.
    """

    @patch("urllib.request.urlopen")
    def test_200_copilot_active(self, mock_open):
        mock_open.return_value = _mock_response(
            {"assignee": {"login": "octocat"}, "plan_type": "business"},
            status=200,
        )
        result = check_copilot_seat("pro_plus_token")

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], 200)
        self.assertEqual(result["data"]["plan_type"], "business")

    @patch("urllib.request.urlopen")
    def test_404_no_copilot_seat(self, mock_open):
        mock_open.side_effect = _mock_http_error(404, "Not Found")
        result = check_copilot_seat("free_token")

        self.assertFalse(result["success"])
        self.assertEqual(result["status"], 404)

    @patch("urllib.request.urlopen")
    def test_403_forbidden(self, mock_open):
        mock_open.side_effect = _mock_http_error(403, "Forbidden")
        result = check_copilot_seat("limited_scope_token")

        self.assertFalse(result["success"])
        self.assertEqual(result["status"], 403)

    @patch("urllib.request.urlopen")
    def test_422_inactive_subscription(self, mock_open):
        mock_open.side_effect = _mock_http_error(422, "Unprocessable Entity")
        result = check_copilot_seat("pending_token")

        self.assertFalse(result["success"])
        self.assertEqual(result["status"], 422)

    @patch("urllib.request.urlopen")
    def test_network_error(self, mock_open):
        mock_open.side_effect = OSError("timeout")
        result = check_copilot_seat("any_token")

        self.assertFalse(result["success"])
        self.assertIsNone(result["status"])


# ---------------------------------------------------------------------------
# determine_pro_plus_status
# ---------------------------------------------------------------------------

class TestDetermineProPlusStatus(unittest.TestCase):
    """Tests for :func:`determine_pro_plus_status`."""

    def test_pro_plan_plus_copilot_200_is_active(self):
        plan = {"success": True, "plan": {"name": "pro"}}
        copilot = {"success": True, "status": 200, "data": {}}
        result = determine_pro_plus_status(plan, copilot)

        self.assertTrue(result["pro_plus_active"])
        self.assertEqual(result["plan_name"], "pro")
        self.assertTrue(result["copilot_seat_active"])

    def test_team_plan_plus_copilot_200_is_active(self):
        plan = {"success": True, "plan": {"name": "team"}}
        copilot = {"success": True, "status": 200, "data": {}}
        result = determine_pro_plus_status(plan, copilot)

        self.assertTrue(result["pro_plus_active"])

    def test_free_plan_is_not_pro_plus(self):
        plan = {"success": True, "plan": {"name": "free"}}
        copilot = {"success": False, "status": 404}
        result = determine_pro_plus_status(plan, copilot)

        self.assertFalse(result["pro_plus_active"])
        self.assertFalse(result["copilot_seat_active"])

    def test_pro_plan_but_copilot_404_is_not_active(self):
        # Paid plan without Copilot seat → Pro+ not confirmed.
        plan = {"success": True, "plan": {"name": "pro"}}
        copilot = {"success": False, "status": 404}
        result = determine_pro_plus_status(plan, copilot)

        self.assertFalse(result["pro_plus_active"])

    def test_copilot_403_is_not_active(self):
        plan = {"success": True, "plan": {"name": "pro"}}
        copilot = {"success": False, "status": 403}
        result = determine_pro_plus_status(plan, copilot)

        self.assertFalse(result["pro_plus_active"])

    def test_plan_check_failure_treated_as_not_active(self):
        plan = {"success": False, "error": "network error"}
        copilot = {"success": False, "status": 401}
        result = determine_pro_plus_status(plan, copilot)

        self.assertFalse(result["pro_plus_active"])
        self.assertEqual(result["plan_name"], "")

    def test_status_dict_contains_expected_keys(self):
        plan = {"success": True, "plan": {"name": "pro"}}
        copilot = {"success": True, "status": 200, "data": {}}
        result = determine_pro_plus_status(plan, copilot)

        for key in EXPECTED_STATUS_KEYS:
            self.assertIn(key, result, f"Missing key: {key}")


# ---------------------------------------------------------------------------
# _build_summary
# ---------------------------------------------------------------------------

class TestBuildSummary(unittest.TestCase):
    """Tests for :func:`_build_summary`."""

    def test_active_contains_active_word(self):
        summary = _build_summary("pro", True, 200)
        self.assertIn("ACTIVE", summary)
        self.assertIn("pro", summary)
        self.assertIn("200", summary)

    def test_422_contains_uncertain(self):
        summary = _build_summary("pro", False, 422)
        self.assertIn("UNCERTAIN", summary)
        self.assertIn("422", summary)

    def test_404_mentions_no_seat(self):
        summary = _build_summary("free", False, 404)
        self.assertIn("404", summary)
        # Summary should indicate inactivity
        self.assertTrue(
            "NOT" in summary or "not" in summary,
            f"Expected 'NOT' or 'not' in summary: {summary}",
        )

    def test_403_mentions_forbidden_or_scope(self):
        summary = _build_summary("free", False, 403)
        self.assertIn("403", summary)

    def test_unknown_status_indicates_unable_to_determine(self):
        summary = _build_summary("pro", False, 500)
        self.assertIn("500", summary)
        self.assertIn("❓", summary)


# ---------------------------------------------------------------------------
# main() integration
# ---------------------------------------------------------------------------

class TestMain(unittest.TestCase):
    """Integration-style tests for :func:`main` (still fully mocked)."""

    def _mock_urlopen_factory(self, plan_data, copilot_data, copilot_status=200):
        """Return a side_effect callable that serves plan then copilot responses."""
        responses = iter([
            _mock_response(plan_data),
            _mock_response(copilot_data, status=copilot_status),
        ])

        def _side_effect(req, *a, **kw):
            return next(responses)

        return _side_effect

    @patch("urllib.request.urlopen")
    def test_exit_code_0_when_pro_plus_active(self, mock_open):
        mock_open.side_effect = self._mock_urlopen_factory(
            plan_data={"login": "octocat", "plan": {"name": "pro"}},
            copilot_data={"plan_type": "individual"},
            copilot_status=200,
        )
        exit_code = main(["--token", "fake_pro_token"])
        self.assertEqual(exit_code, 0)

    @patch("urllib.request.urlopen")
    def test_exit_code_1_when_copilot_404(self, mock_open):
        responses = [
            _mock_response({"login": "freeuser", "plan": {"name": "free"}}),
        ]

        def _se(req, *a, **kw):
            if "/copilot" in req.full_url:
                raise _mock_http_error(404, "Not Found")
            return responses.pop(0)

        mock_open.side_effect = _se
        exit_code = main(["--token", "free_token"])
        self.assertEqual(exit_code, 1)

    def test_exit_code_2_when_no_token(self):
        # Remove GITHUB_TOKEN from environment if present.
        env_backup = os.environ.pop("GITHUB_TOKEN", None)
        try:
            exit_code = main(["--token", ""])
            self.assertEqual(exit_code, 2)
        finally:
            if env_backup is not None:
                os.environ["GITHUB_TOKEN"] = env_backup

    @patch("urllib.request.urlopen")
    def test_json_output_is_valid_json(self, mock_open):
        mock_open.side_effect = self._mock_urlopen_factory(
            plan_data={"login": "octocat", "plan": {"name": "pro"}},
            copilot_data={"plan_type": "individual"},
            copilot_status=200,
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            main(["--token", "fake_token", "--json"])

        output = buf.getvalue()
        parsed = json.loads(output)  # Should not raise.
        self.assertIn("status", parsed)
        self.assertIn("plan_check", parsed)
        self.assertIn("copilot_check", parsed)


if __name__ == "__main__":
    unittest.main()
