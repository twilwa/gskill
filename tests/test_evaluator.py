"""Tests for evaluator command selection and task runner behavior."""

from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from src.evaluator import (
    _build_test_command,
    _run_local_checkout_verifier,
    _task_to_local_checkout,
    make_evaluator,
)
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

    setup_command = (
        "python -c \"from pathlib import Path; Path('setup.marker').write_text('setup')\""
    )
    install_command = (
        "python -c \"from pathlib import Path; "
        "assert Path('setup.marker').read_text() == 'setup'; "
        "Path('install.marker').write_text('install')\""
    )
    verifier_command = (
        "python -c \"from pathlib import Path; "
        "assert Path('setup.marker').read_text() == 'setup'; "
        "assert Path('install.marker').read_text() == 'install'; "
        "assert Path('src/math_utils.py').read_text() == 'def add(a, b):\\n    return a - b\\n'\""
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

        if (
            setup_command in command
            and install_command in command
            and verifier_command in command
        ):
            (cwd / "setup.marker").write_text("setup")
            (cwd / "install.marker").write_text("install")
            (cwd / ".gskill_stage").write_text("verifier")
            return subprocess.CompletedProcess(cmd, 0, stdout="install", stderr="")

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
        environment=EnvironmentSpec(
            kind="local_checkout",
            ref=str(checkout),
            setup_commands=(setup_command,),
            install_commands=(install_command,),
        ),
        verifier=VerifierSpec(
            kind="shell_command",
            commands=(verifier_command,),
        ),
        metadata={"snapshot_path": str(checkout)},
    )

    score, info = evaluator("candidate skill", task)

    assert score == 1.0
    assert info["instance_id"] == "local-1"
    assert info["test_failure_reason"] == "shell_command_passed"

    stage_calls = []
    for call in calls:
        if call["kind"] != "subprocess":
            continue
        command = call["command"]
        if "git apply" in command or "patch -p1" in command:
            stage_calls.append("patch_apply")
        elif (
            setup_command in command
            and install_command in command
            and verifier_command in command
            and command.index(setup_command) < command.index(install_command) < command.index(verifier_command)
        ):
            stage_calls.append("bootstrap_and_verifier")
    assert stage_calls == ["patch_apply", "bootstrap_and_verifier"]

    subprocess_calls = [
        call for call in calls if call["kind"] == "subprocess" and "pytest" not in call["command"]
    ]
    assert subprocess_calls
    assert all(call["cwd"] != checkout for call in subprocess_calls)
    assert (checkout / "src" / "math_utils.py").read_text() == "def add(a, b):\n    return a + b\n"


@pytest.mark.parametrize(
    ("failed_stage", "stage_command"),
    [
        (
            "setup",
            "python -c \"from pathlib import Path; raise SystemExit('setup failed')\"",
        ),
        (
            "install",
            "python -c \"from pathlib import Path; raise SystemExit('install failed')\"",
        ),
    ],
)
def test_evaluator_reports_stage_specific_failure_for_bootstrap_commands(
    monkeypatch, tmp_path, failed_stage, stage_command
):
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

        if stage_command in command:
            (cwd / ".gskill_stage").write_text(failed_stage)
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr=f"{failed_stage} failed")

        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("src.evaluator.get_model", fake_get_model)
    monkeypatch.setattr("src.evaluator.get_agent", fake_get_agent)
    monkeypatch.setattr("src.evaluator.subprocess.run", fake_run)

    evaluator = make_evaluator(agent_model="openai/test-model")
    task = TaskSpec(
        id=f"local-{failed_stage}",
        family="mutation",
        source="python-mutation",
        repo_name="acme/commerce-api",
        problem_statement="Flip the add implementation.",
        environment=EnvironmentSpec(
            kind="local_checkout",
            ref=str(checkout),
            setup_commands=(stage_command,) if failed_stage == "setup" else (),
            install_commands=(stage_command,) if failed_stage == "install" else (),
        ),
        verifier=VerifierSpec(
            kind="shell_command",
            commands=(
                "python -c \"from pathlib import Path; "
                "assert Path('src/math_utils.py').read_text() == 'def add(a, b):\\n    return a - b\\n'\"",
            ),
        ),
        metadata={"snapshot_path": str(checkout)},
    )

    score, info = evaluator("candidate skill", task)

    assert score == 0.0
    assert info["instance_id"] == f"local-{failed_stage}"
    assert info["test_failure_reason"].startswith(failed_stage)
    assert info["test_failure_reason"].endswith("_failed")

    stage_names = []
    for call in calls:
        if call["kind"] != "subprocess":
            continue
        command = call["command"]
        if "git apply" in command or "patch -p1" in command:
            stage_names.append("patch_apply")
        elif stage_command in command:
            stage_names.append(failed_stage)
        elif "assert Path('src/math_utils.py')" in command:
            stage_names.append("verifier")
    assert stage_names == ["patch_apply", failed_stage]


def test_local_checkout_verifier_preserves_shell_state_across_bootstrap_stages(tmp_path):
    snapshot = tmp_path / "snapshot"
    (snapshot / "src").mkdir(parents=True)
    (snapshot / "src" / "math_utils.py").write_text(
        "def add(a, b):\n    return a + b\n"
    )
    subprocess.run(
        ["git", "init"],
        cwd=snapshot,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    subprocess.run(
        ["git", "add", "src/math_utils.py"],
        cwd=snapshot,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    original_source = "def add(a, b):\n    return a + b\n"
    mutated_source = "def add(a, b):\n    return a - b\n"
    (snapshot / "src" / "math_utils.py").write_text(mutated_source)
    patch = subprocess.run(
        ["git", "diff", "--binary", "--no-ext-diff", "--", "src/math_utils.py"],
        cwd=snapshot,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    ).stdout
    (snapshot / "src" / "math_utils.py").write_text(original_source)

    passed, reason = _run_local_checkout_verifier(
        snapshot,
        patch,
        setup_commands=(
            "export GSKILL_SETUP_STATE=ready",
            "export GSKILL_NUMBER=7",
        ),
        install_commands=(
            'test "$GSKILL_SETUP_STATE" = ready',
            'test "$GSKILL_NUMBER" = 7',
            "export GSKILL_INSTALL_STATE=done",
        ),
        verifier_commands=[
            'test "$GSKILL_SETUP_STATE" = ready',
            'test "$GSKILL_INSTALL_STATE" = done',
            "python -c \"from pathlib import Path; "
            "assert Path('src/math_utils.py').read_text() == 'def add(a, b):\\n    return a - b\\n'\"",
        ],
        timeout=30,
    )

    assert passed is True
    assert reason == "shell_command_passed"
    assert (snapshot / "src" / "math_utils.py").read_text() == "def add(a, b):\n    return a + b\n"


def test_task_to_local_checkout_keeps_bootstrap_commands_for_compat_dict(tmp_path):
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()

    instance = _task_to_local_checkout(
        {
            "instance_id": "compat-1",
            "problem_statement": "Run bootstrap before verifier.",
            "snapshot_path": str(snapshot),
            "setup_commands": ["echo setup"],
            "install_commands": ["echo install"],
            "commands": ["echo verify"],
        }
    )

    assert instance is not None
    assert instance["setup_commands"] == ("echo setup",)
    assert instance["install_commands"] == ("echo install",)
    assert instance["verifier_commands"] == ["echo verify"]
