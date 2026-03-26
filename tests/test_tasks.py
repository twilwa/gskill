"""Tests for canonical task loading and bundle assembly."""

from __future__ import annotations

from pathlib import Path

import pytest

from src import tasks


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


def test_build_task_bundle_rejects_unknown_sources():
    with pytest.raises(ValueError, match="Unknown task source"):
        tasks.build_task_bundle(
            repo_name="acme/commerce-api",
            source_names=["does-not-exist"],
        )
