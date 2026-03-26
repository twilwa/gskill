# ABOUTME: Exercises the Typer CLI entry points for task previews and pipeline wiring.
# ABOUTME: Verifies canonical task previews use the task-source layer and emit stable JSON.
"""Tests for the gskill CLI."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

import main
from src.tasks import EnvironmentSpec, TaskBundle, TaskSpec, VerifierSpec


def _bundle_for_preview() -> TaskBundle:
    tasks = [
        TaskSpec(
            id="task-1",
            family="benchmark",
            source="swe-smith",
            repo_name="pallets/jinja",
            problem_statement="Fix template rendering.",
            environment=EnvironmentSpec(kind="swebench_docker", ref="swesmith/pallets__jinja.123"),
            verifier=VerifierSpec(
                kind="test_selectors",
                selectors=["tests/test_core.py::test_render"],
            ),
            metadata={"image_name": "swebench/jinja:latest"},
        ),
        TaskSpec(
            id="task-2",
            family="benchmark",
            source="swe-smith",
            repo_name="pallets/jinja",
            problem_statement="Keep whitespace handling correct.",
            environment=EnvironmentSpec(kind="swebench_docker", ref="swesmith/pallets__jinja.456"),
            verifier=VerifierSpec(
                kind="test_selectors",
                selectors=["tests/test_core.py::test_keep_whitespace"],
            ),
            metadata={"image_name": "swebench/jinja:latest"},
        ),
    ]
    return TaskBundle(
        tasks=tasks,
        train=tasks[:1],
        val=[],
        test=tasks[1:],
        provenance={"source_counts": {"swe-smith": 2}, "sources": ["swe-smith"]},
        rejections=[],
    )


def _history_bundle(checkout_path: str) -> TaskBundle:
    task = TaskSpec(
        id="history-1",
        family="history_replay",
        source="python-history-replay",
        repo_name="acme/repo",
        problem_statement="Restore the replayed fix.",
        environment=EnvironmentSpec(kind="local_checkout", ref="/tmp/history-1"),
        verifier=VerifierSpec(kind="shell_command", commands=("uv run pytest -q",)),
        metadata={
            "history_replay": {
                "fixed_commit": "abc123",
                "parent_commit": "def456",
                "subject": "fix: restore behavior",
                "changed_paths": ["src/service.py"],
            }
        },
        mutable_paths=("src/service.py",),
    )
    return TaskBundle(
        tasks=[task],
        train=[task],
        val=[],
        test=[],
        provenance={
            "source_counts": {"python-history-replay": 1},
            "sources": ["python-history-replay"],
            "history_replay_source": {
                "kind": "python",
                "checkout_path": checkout_path,
            },
        },
        rejections=[],
    )


def _preview_file(tmp_path: Path) -> Path:
    files = list(tmp_path.glob("*--tasks-*.json"))
    assert len(files) == 1
    return files[0]


def _legacy_rows() -> list[dict[str, object]]:
    return [
        {
            "instance_id": "legacy-1",
            "repo": "swesmith/pallets__jinja.123",
            "problem_statement": "Legacy preview row.",
        }
    ]


def test_tasks_command_builds_canonical_preview_bundle(monkeypatch, tmp_path):
    recorded: dict[str, object] = {}

    def fake_build_task_bundle(
        repo_name: str,
        repo_url=None,
        checkout_path=None,
        source_names=None,
        limit: int = 300,
        train: float = 0.67,
        val: float = 0.17,
        scratch_dir=None,
    ):
        recorded["repo_name"] = repo_name
        recorded["repo_url"] = repo_url
        recorded["checkout_path"] = checkout_path
        recorded["source_names"] = source_names
        recorded["limit"] = limit
        return _bundle_for_preview()

    monkeypatch.setattr("src.tasks.build_task_bundle", fake_build_task_bundle)
    monkeypatch.setattr("src.tasks.load_tasks", lambda repo, n=300: _legacy_rows())
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(main.app, ["tasks", "pallets/jinja", "--limit", "2"])

    assert result.exit_code == 0
    assert recorded == {
        "repo_name": "pallets/jinja",
        "repo_url": None,
        "checkout_path": None,
        "source_names": None,
        "limit": 2,
    }

    payload = json.loads(_preview_file(tmp_path).read_text())
    assert set(payload) == {"tasks", "train", "val", "test", "provenance", "rejections"}
    assert payload["provenance"] == {"source_counts": {"swe-smith": 2}, "sources": ["swe-smith"]}
    assert payload["tasks"][0]["id"] == "task-1"
    assert payload["tasks"][1]["problem_statement"] == "Keep whitespace handling correct."
    assert payload["train"][0]["id"] == "task-1"
    assert payload["test"][0]["id"] == "task-2"


def test_tasks_command_passes_repo_native_preview_context(monkeypatch, tmp_path):
    recorded: dict[str, object] = {}

    def fake_build_task_bundle(
        repo_name: str,
        repo_url=None,
        checkout_path=None,
        source_names=None,
        limit: int = 300,
        train: float = 0.67,
        val: float = 0.17,
        scratch_dir=None,
    ):
        recorded["repo_name"] = repo_name
        recorded["repo_url"] = repo_url
        recorded["checkout_path"] = checkout_path
        recorded["source_names"] = source_names
        recorded["limit"] = limit
        return _history_bundle(str(checkout_path))

    monkeypatch.setattr("src.tasks.build_task_bundle", fake_build_task_bundle)
    monkeypatch.setattr("src.tasks.load_tasks", lambda repo, n=300: _legacy_rows())
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        main.app,
        [
            "tasks",
            "acme/repo",
            "--task-source",
            "python-history-replay",
            "--checkout-path",
            "/tmp/repo",
            "--limit",
            "1",
        ],
    )

    assert result.exit_code == 0
    assert recorded == {
        "repo_name": "acme/repo",
        "repo_url": None,
        "checkout_path": "/tmp/repo",
        "source_names": ["python-history-replay"],
        "limit": 1,
    }

    payload = json.loads(_preview_file(tmp_path).read_text())
    assert payload["provenance"]["history_replay_source"] == {
        "kind": "python",
        "checkout_path": "/tmp/repo",
    }
    assert payload["tasks"][0]["source"] == "python-history-replay"
    assert payload["tasks"][0]["environment"]["kind"] == "local_checkout"
    assert payload["tasks"][0]["metadata"]["history_replay"]["fixed_commit"] == "abc123"


def test_tasks_command_list_mode_prints_task_summaries(monkeypatch, tmp_path):
    monkeypatch.setattr("src.tasks.build_task_bundle", lambda **_: _bundle_for_preview())
    monkeypatch.setattr("src.tasks.load_tasks", lambda repo, n=300: _legacy_rows())
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        main.app,
        ["tasks", "pallets/jinja", "--limit", "2", "--list"],
    )

    assert result.exit_code == 0
    assert "task-1 [swe-smith:benchmark]" in result.stdout
    assert "task-2 [swe-smith:benchmark]" in result.stdout
    assert _preview_file(tmp_path).exists()
