"""Operator policy, plugin compatibility, limits and optional-import coverage."""

import json
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

from langgraph_system_generator.generator import nodes
from langgraph_system_generator.qa.registry import (
    QARepairRegistry,
    SpecialistReviewerRegistration,
    get_qa_repair_registry,
)
from langgraph_system_generator.qa.specialist_models import (
    REVIEWER_ID,
    ModelReviewResponse,
)
from langgraph_system_generator.qa.specialist_review import (
    review_candidate,
)
from langgraph_system_generator.utils.config import Settings
from tests.unit.test_semantic_review_contract import context, response
from tests.unit.test_semantic_review_pipeline import install_reviewer, starting_state


def test_registry_clone_order_replacement_empty_and_existing_plugins(monkeypatch):
    module = types.ModuleType("semantic_test_plugin")

    def register(value):
        value.register_specialist_reviewer(
            SpecialistReviewerRegistration(
                "fake_second", "1", ("generated_cells",), lambda config: None
            )
        )

    module.register_qa_repair_plugins = register
    monkeypatch.setitem(sys.modules, module.__name__, module)
    value = get_qa_repair_registry([module.__name__])
    assert value.registered_specialist_reviewer_ids() == [REVIEWER_ID, "fake_second"]
    before = (value.registered_validator_ids(), value.registered_repair_routine_ids())
    clone = value.clone()
    clone.register_specialist_reviewer(
        SpecialistReviewerRegistration(
            REVIEWER_ID, "2", ("generated_cells",), lambda config: None
        )
    )
    assert (
        clone.registered_specialist_reviewer_ids()
        == value.registered_specialist_reviewer_ids()
    )
    assert value.specialist_reviewer(REVIEWER_ID).version == "1"
    assert clone.specialist_reviewer(REVIEWER_ID).version == "2"
    clone.disable_specialist_reviewer("fake_second")
    assert "fake_second" in value.registered_specialist_reviewer_ids()
    assert (
        clone.registered_validator_ids(),
        clone.registered_repair_routine_ids(),
    ) == before
    assert (
        QARepairRegistry(specialist_reviewers=())
        .clone()
        .registered_specialist_reviewer_ids()
        == []
    )


@pytest.mark.parametrize("mode", ["blocking", "on", "", "ADVISORY"])
def test_mode_accepts_exactly_off_or_advisory(mode):
    with pytest.raises(ValueError):
        Settings(_env_file=None, lnf_specialist_qa_mode=mode)


async def test_policy_is_host_owned_snapshot_and_feedback_is_once(monkeypatch):
    calls, _ = install_reviewer(monkeypatch)
    value = starting_state()
    monkeypatch.setattr(nodes.settings, "lnf_specialist_qa_mode", "advisory")
    value.update(await nodes.review_policy_node(value))
    monkeypatch.setattr(nodes.settings, "lnf_specialist_qa_mode", "off")
    result = await review_candidate(value)
    assert result.status == "reviewed" and len(calls) == 1
    value["semantic_review_feedback"] = result
    assert (await review_candidate(value)) == result and len(calls) == 1
    value["user_prompt"] = "Replacement requirement"
    stale = await review_candidate(value)
    assert stale.status == "incomplete" and stale.findings == () and len(calls) == 1
    value.update(await nodes.review_policy_node(value))
    assert value["semantic_review_policy"].mode == "off"
    assert await review_candidate(value) is None


@pytest.mark.parametrize(
    "change", ["findings", "references", "suggestions", "message", "quote", "severity"]
)
def test_model_field_bounds_and_no_severity_authority(change):
    ctx = context()
    payload = response(ctx).model_dump(mode="json")
    finding = payload["findings"][0]
    if change == "findings":
        payload["findings"] *= 9
    elif change == "references":
        finding["references"] *= 4
    elif change == "suggestions":
        finding["suggestions"] *= 3
    elif change == "quote":
        finding["references"][0]["quote"] = "x" * 161
    elif change == "severity":
        finding["severity"] = "error"
    else:
        finding["message"] = "x" * 401
    with pytest.raises(ValueError):
        ModelReviewResponse.model_validate_json(json.dumps(payload))


def test_core_state_models_import_without_optional_model_notebook_modules():
    root = str(Path(__file__).parents[2] / "src")
    code = """
import sys, importlib.abc
sys.path.insert(0, sys.argv[1])
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'langchain_openai','nbformat','langgraph','langsmith'}:
            raise AssertionError('optional import: ' + fullname)
sys.meta_path.insert(0, Guard())
from langgraph_system_generator.generator.state import GeneratorState
from langgraph_system_generator.qa.specialist_models import SemanticReviewPolicy
assert SemanticReviewPolicy().mode == 'off'
print('core contracts import without optional SDKs')
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", code, root],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_separate_process_reads_own_operator_policy():
    root = str(Path(__file__).parents[2] / "src")
    code = "import sys; sys.path.insert(0,sys.argv[1]); from langgraph_system_generator.utils.config import Settings; print(Settings(_env_file=None).lnf_specialist_qa_mode)"
    for mode in ("off", "advisory"):
        env = {**os.environ, "LNF_SPECIALIST_QA_MODE": mode, "LNF_DISABLE_DOTENV": "1"}
        result = subprocess.run(
            [sys.executable, "-I", "-c", code, root],
            check=False,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert result.stdout.strip() == mode
