"""Tests for evaluator command selection and task runner behavior."""

from __future__ import annotations

from pathlib import Path
import subprocess

from src.evaluator import _build_test_command, make_evaluator
from src.tasks import EnvironmentSpec, TaskSpec, VerifierSpec


def test_build_test_command_for_pytest_tasks():
    command, mode = _build_test_command(
        {
            "repo": "swesmith/pallets__jinja.ada0a9a6",
            "FAIL_TO_PASS": ["tests/test_nativetypes.py::test_constant_dunder"],
        }
    )

    assert mode == "pytest"
    assert "python -m pytest" in command
    assert "tests/test_nativetypes.py::test_constant_dunder" in command


def test_build_test_command_for_go_tasks():
    command, mode = _build_test_command(
        {
            "repo": "swesmith/blevesearch__bleve.f2876b5e",
            "FAIL_TO_PASS": ["TestGeoDistanceIssue1301", "ExampleNew"],
        }
    )

    assert mode == "go_test"
    assert "go test ./..." in command
    assert "TestGeoDistanceIssue1301|ExampleNew" in command


def test_evaluator_reports_unsupported_runner_for_non_swebench_tasks():
    evaluator = make_evaluator(agent_model="openai/test-model")
    task = TaskSpec(
        id="local-1",
        family="terminal",
        source="repo-terminal",
        repo_name="acme/commerce-api",
        problem_statement="Run the local verification command.",
        environment=EnvironmentSpec(kind="local_checkout", ref="HEAD"),
        verifier=VerifierSpec(kind="test_selectors", selectors=["tests/test_app.py::test_case"]),
        metadata={},
    )

    score, info = evaluator("candidate skill", task)

    assert score == 0.0
    assert info["instance_id"] == "local-1"
    assert info["test_failure_reason"] == "unsupported_runner"
