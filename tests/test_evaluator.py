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


def test_evaluator_runs_local_checkout_tasks_in_a_copied_snapshot(monkeypatch, tmp_path):
    checkout = tmp_path / "checkout"
    (checkout / "src").mkdir(parents=True)
    (checkout / "tests").mkdir()
    (checkout / "src" / "math_utils.py").write_text(
        "def add(a, b):\n    return a + b\n"
    )
    (checkout / "tests" / "test_math_utils.py").write_text(
        "from src.math_utils import add\n\n\n"
        "def test_add():\n"
        "    assert add(1, 2) == 3\n"
    )

    patch = """diff --git a/src/math_utils.py b/src/math_utils.py
index 0000000..1111111 100644
--- a/src/math_utils.py
+++ b/src/math_utils.py
@@
-def add(a, b):
-    return a + b
+def add(a, b):
+    return a - b
"""
    calls: list[dict[str, object]] = []

    class FakeAgent:
        def run(self, prompt: str):
            calls.append({"kind": "agent", "prompt": prompt})
            return {"submission": patch}

    def fake_get_model(config=None):
        calls.append({"kind": "model", "config": config})
        return object()

    def fake_get_agent(model, env, config, default_type="default"):
        calls.append({"kind": "agent_factory", "config": config})
        return FakeAgent()

    def fake_run(cmd, *args, **kwargs):
        command = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
        cwd = Path(kwargs.get("cwd") or checkout)
        calls.append({"kind": "subprocess", "command": command, "cwd": cwd})

        if "git apply" in command or "patch -p1" in command:
            path = cwd / "src" / "math_utils.py"
            path.write_text("def add(a, b):\n    return a - b\n")
            return subprocess.CompletedProcess(cmd, 0, stdout="applied", stderr="")

        if "pytest" in command:
            source = (cwd / "src" / "math_utils.py").read_text()
            passed = "return a - b" in source
            return subprocess.CompletedProcess(
                cmd,
                0 if passed else 1,
                stdout="passed" if passed else "failed",
                stderr="",
            )

        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("src.evaluator.get_model", fake_get_model)
    monkeypatch.setattr("src.evaluator.get_agent", fake_get_agent)
    monkeypatch.setattr("src.evaluator.subprocess.run", fake_run)

    evaluator = make_evaluator(agent_model="openai/test-model")
    task = TaskSpec(
        id="local-1",
        family="mutation",
        source="python-mutation",
        repo_name="acme/commerce-api",
        problem_statement="Flip the add implementation.",
        environment=EnvironmentSpec(kind="local_checkout", ref=str(checkout)),
        verifier=VerifierSpec(
            kind="shell_command",
            commands=("uv run pytest",),
        ),
        metadata={"snapshot_path": str(checkout)},
    )

    score, info = evaluator("candidate skill", task)

    assert score == 1.0
    assert info["instance_id"] == "local-1"
    assert info["test_failure_reason"] == "shell_command_passed"

    verifier_calls = [
        call for call in calls if call["kind"] == "subprocess" and "pytest" in call["command"]
    ]
    assert verifier_calls
    verifier_call = verifier_calls[-1]
    assert verifier_call["cwd"] != checkout
    assert (checkout / "src" / "math_utils.py").read_text() == "def add(a, b):\n    return a + b\n"
