"""Tests for canonical task loading and bundle assembly."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src import tasks


def _run_git(args: list[str], cwd: Path) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def _create_python_history_repo(root: Path) -> tuple[Path, str, str]:
    repo_path = root / "history-replay-repo"
    repo_path.mkdir()
    _run_git(["init", "-b", "main"], cwd=repo_path)
    _run_git(["config", "user.name", "Test User"], cwd=repo_path)
    _run_git(["config", "user.email", "test@example.com"], cwd=repo_path)

    (repo_path / "src").mkdir()
    (repo_path / "tests").mkdir()
    (repo_path / "src" / "__init__.py").write_text("")
    (repo_path / "src" / "calculator.py").write_text(
        "def add(left: int, right: int) -> int:\n"
        "    return left - right\n"
    )
    (repo_path / "tests" / "test_calculator.py").write_text(
        "from src.calculator import add\n\n"
        "def test_add():\n"
        "    assert add(2, 3) == 5\n"
    )

    _run_git(
        ["add", "src/__init__.py", "src/calculator.py", "tests/test_calculator.py"],
        cwd=repo_path,
    )
    _run_git(["commit", "-m", "feat: add calculator"], cwd=repo_path)

    (repo_path / "src" / "calculator.py").write_text(
        "def add(left: int, right: int) -> int:\n"
        "    return left + right\n"
    )
    _run_git(["add", "src/calculator.py"], cwd=repo_path)
    _run_git(["commit", "-m", "fix: correct calculator addition"], cwd=repo_path)

    fixed_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_path,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    ).stdout.strip()
    parent_commit = subprocess.run(
        ["git", "rev-parse", "HEAD^"],
        cwd=repo_path,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    ).stdout.strip()
    return repo_path, fixed_commit, parent_commit


def test_swe_smith_source_collects_canonical_tasks(monkeypatch):
    rows = [
        {
            "instance_id": "jinja-1",
            "repo": "swesmith/pallets__jinja.ada0a9a6",
            "problem_statement": "Fix template rendering.",
            "image_name": "swebench/jinja:latest",
            "FAIL_TO_PASS": ["tests/test_core.py::test_render"],
            "PASS_TO_PASS": ["tests/test_core.py::test_keep_working"],
        }
    ]

    monkeypatch.setattr(tasks, "load_dataset", lambda name, split: rows)

    source = tasks.get_task_source("swe-smith")
    collected = source.collect(tasks.TaskSourceRequest(repo_name="pallets/jinja", limit=1))

    assert len(collected) == 1
    task = collected[0]
    assert task.id == "jinja-1"
    assert task.source == "swe-smith"
    assert task.family == "benchmark"
    assert task.problem_statement == "Fix template rendering."
    assert task.environment.kind == "swebench_docker"
    assert task.environment.ref == "swesmith/pallets__jinja.ada0a9a6"
    assert task.verifier.kind == "test_selectors"
    assert task.verifier.selectors == ["tests/test_core.py::test_render"]
    assert task.metadata["image_name"] == "swebench/jinja:latest"


def test_build_task_bundle_records_source_counts(monkeypatch):
    collected = [
        tasks.TaskSpec(
            id=f"task-{index}",
            family="benchmark",
            source="swe-smith",
            repo_name="acme/commerce-api",
            problem_statement=f"Problem {index}",
            environment=tasks.EnvironmentSpec(kind="swebench_docker", ref=f"ref-{index}"),
            verifier=tasks.VerifierSpec(kind="test_selectors", selectors=[f"tests/test_{index}.py::test_case"]),
            metadata={"index": index},
        )
        for index in range(5)
    ]

    class FakeSource:
        name = "swe-smith"

        def collect(self, repo_name: str, limit: int = 300):
            assert repo_name == "acme/commerce-api"
            assert limit == 5
            return collected

    monkeypatch.setattr(tasks, "get_task_source", lambda name: FakeSource())

    bundle = tasks.build_task_bundle(
        repo_name="acme/commerce-api",
        source_names=["swe-smith"],
        limit=5,
    )

    assert [task.id for task in bundle.tasks] == [task.id for task in collected]
    assert len(bundle.train) == 3
    assert len(bundle.val) == 0
    assert len(bundle.test) == 2
    assert bundle.provenance["source_counts"] == {"swe-smith": 5}


def test_build_task_bundle_passes_repo_context_to_python_mutation_source(monkeypatch, tmp_path):
    recorded: dict[str, object] = {}

    class FakeSource:
        name = "python-mutation"

        def collect(self, request, limit: int = 300):
            recorded["request"] = request
            assert request.limit == 2
            assert limit == 2
            snapshot_path = request.scratch_dir / "snapshots" / "mutation-1"
            return [
                tasks.TaskSpec(
                    id="mutation-1",
                    family="mutation",
                    source="python-mutation",
                    repo_name=request.repo_name,
                    problem_statement="Break the add function.",
                    environment=tasks.EnvironmentSpec(
                        kind="local_checkout",
                        ref=str(snapshot_path),
                    ),
                    verifier=tasks.VerifierSpec(
                        kind="shell_command",
                        commands=("uv run pytest",),
                    ),
                    metadata={
                        "mutation_source": {
                            "kind": "python",
                            "validation_command": "uv run pytest",
                        },
                        "snapshot_path": str(snapshot_path),
                    },
                )
            ]

    monkeypatch.setattr(tasks, "get_task_source", lambda name: FakeSource())

    bundle = tasks.build_task_bundle(
        repo_name="acme/commerce-api",
        repo_url="https://github.com/acme/commerce-api",
        scratch_dir=tmp_path,
        source_names=["python-mutation"],
        limit=2,
    )

    request = recorded["request"]
    assert request.repo_name == "acme/commerce-api"
    assert request.repo_url == "https://github.com/acme/commerce-api"
    assert request.limit == 2
    assert request.scratch_dir == tmp_path
    assert bundle.provenance["source_counts"] == {"python-mutation": 1}
    assert bundle.provenance["sources"] == ["python-mutation"]
    assert bundle.tasks[0].environment.kind == "local_checkout"
    assert Path(bundle.tasks[0].environment.ref).name == "mutation-1"


def test_build_task_bundle_records_python_history_replay_commit_provenance(tmp_path):
    repo_path, fixed_commit, parent_commit = _create_python_history_repo(tmp_path)

    bundle = tasks.build_task_bundle(
        repo_name="acme/calculator",
        checkout_path=str(repo_path),
        source_names=["python-history-replay"],
        limit=1,
        scratch_dir=str(tmp_path / "scratch"),
    )

    assert len(bundle.tasks) == 1
    task = bundle.tasks[0]
    assert task.source == "python-history-replay"
    assert task.environment.kind == "local_checkout"
    assert task.verifier.kind == "shell_command"
    assert task.metadata["history_replay"] == {
        "fixed_commit": fixed_commit,
        "parent_commit": parent_commit,
        "subject": "fix: correct calculator addition",
        "changed_paths": ["src/calculator.py"],
    }
    assert bundle.provenance["source_counts"] == {"python-history-replay": 1}
    assert bundle.provenance["sources"] == ["python-history-replay"]
    assert bundle.provenance["history_replay_source"] == {
        "kind": "python",
        "checkout_path": str(repo_path),
    }


def test_build_task_bundle_rejects_unknown_sources():
    with pytest.raises(ValueError, match="Unknown task source"):
        tasks.build_task_bundle(
            repo_name="acme/commerce-api",
            source_names=["does-not-exist"],
        )
