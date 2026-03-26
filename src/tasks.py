"""Task loading, canonical task models, and bundle assembly for gskill."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from datasets import load_dataset

DATASET_NAME = "SWE-bench/SWE-smith"
DEFAULT_TASK_SOURCE = "swe-smith"


@dataclass(frozen=True)
class EnvironmentSpec:
    """Describe the environment needed to execute a task."""

    kind: str
    ref: str = ""
    setup_commands: tuple[str, ...] = ()
    install_commands: tuple[str, ...] = ()
    timeout_seconds: int | None = None


@dataclass(frozen=True)
class VerifierSpec:
    """Describe how task success is verified."""

    kind: str
    commands: tuple[str, ...] = ()
    selectors: list[str] = field(default_factory=list)
    pass_condition: str = ""
    timeout_seconds: int | None = None


@dataclass(frozen=True)
class TaskSpec:
    """Canonical optimization task representation."""

    id: str
    family: str
    source: str
    repo_name: str
    problem_statement: str
    environment: EnvironmentSpec
    verifier: VerifierSpec
    metadata: dict[str, Any] = field(default_factory=dict)
    mutable_paths: tuple[str, ...] = ()
    difficulty: str | None = None
    weight: float = 1.0


@dataclass(frozen=True)
class TaskBundle:
    """Canonical task bundle with train/val/test splits and provenance."""

    tasks: list[TaskSpec]
    train: list[TaskSpec]
    val: list[TaskSpec]
    test: list[TaskSpec]
    provenance: dict[str, Any] = field(default_factory=dict)
    rejections: list[dict[str, Any]] = field(default_factory=list)


class TaskSource(Protocol):
    """Collect tasks for a repository from a named source."""

    name: str

    def collect(self, repo_name: str, limit: int = 300) -> list[TaskSpec]:
        """Return canonical tasks for the given repository."""


def _filter_swe_smith_records(repo_name: str, n: int = 300) -> list[dict[str, Any]]:
    """Load raw SWE-smith records filtered by repo_name."""

    ds = load_dataset(DATASET_NAME, split="train")
    slug = repo_name.replace("/", "__")
    records = [dict(row) for row in ds if slug in row["repo"]]
    if not records:
        raise ValueError(
            f"No tasks found for repo '{repo_name}' in {DATASET_NAME}. "
            f"Use the full 'owner/repo' format, e.g., 'pallets/jinja'."
        )
    return records[:n]


class SweSmithSource:
    """Canonical task adapter for the SWE-smith dataset."""

    name = DEFAULT_TASK_SOURCE

    def collect(self, repo_name: str, limit: int = 300) -> list[TaskSpec]:
        return [self._to_task(repo_name, row) for row in _filter_swe_smith_records(repo_name, n=limit)]

    @staticmethod
    def _to_task(repo_name: str, row: dict[str, Any]) -> TaskSpec:
        return TaskSpec(
            id=row.get("instance_id", "unknown"),
            family="benchmark",
            source=DEFAULT_TASK_SOURCE,
            repo_name=repo_name,
            problem_statement=row.get("problem_statement", ""),
            environment=EnvironmentSpec(
                kind="swebench_docker",
                ref=row.get("repo", ""),
            ),
            verifier=VerifierSpec(
                kind="test_selectors",
                selectors=list(row.get("FAIL_TO_PASS", [])),
            ),
            metadata=dict(row),
        )


_TASK_SOURCES: dict[str, TaskSource] = {
    DEFAULT_TASK_SOURCE: SweSmithSource(),
}


def get_task_source(name: str) -> TaskSource:
    """Resolve a named task source."""

    try:
        return _TASK_SOURCES[name]
    except KeyError as exc:
        available = ", ".join(sorted(_TASK_SOURCES))
        raise ValueError(f"Unknown task source '{name}'. Available sources: {available}") from exc


def load_tasks(repo_name: str, n: int = 300) -> list[dict]:
    """Load raw SWE-smith tasks for compatibility with the existing pipeline."""

    return _filter_swe_smith_records(repo_name, n=n)


def split_tasks(
    tasks: list[TaskSpec] | list[dict], train: float = 0.67, val: float = 0.17
) -> tuple[list[TaskSpec] | list[dict], list[TaskSpec] | list[dict], list[TaskSpec] | list[dict]]:
    """Deterministically split tasks into train/val/test sets."""

    n = len(tasks)
    n_train = int(n * train)
    n_val = int(n * val)
    return (
        tasks[:n_train],
        tasks[n_train : n_train + n_val],
        tasks[n_train + n_val :],
    )


def build_task_bundle(
    repo_name: str,
    source_names: list[str] | None = None,
    limit: int = 300,
    train: float = 0.67,
    val: float = 0.17,
) -> TaskBundle:
    """Collect tasks from named sources and assemble a canonical bundle."""

    selected_sources = source_names or [DEFAULT_TASK_SOURCE]
    collected: list[TaskSpec] = []
    source_counts: dict[str, int] = {}
    rejections: list[dict[str, Any]] = []

    for source_name in selected_sources:
        source = get_task_source(source_name)
        try:
            source_tasks = source.collect(repo_name, limit=limit)
        except ValueError as exc:
            rejections.append({"source": source_name, "reason": str(exc)})
            raise
        collected.extend(source_tasks)
        source_counts[source_name] = len(source_tasks)

    train_tasks, val_tasks, test_tasks = split_tasks(collected, train=train, val=val)
    return TaskBundle(
        tasks=collected,
        train=list(train_tasks),
        val=list(val_tasks),
        test=list(test_tasks),
        provenance={
            "source_counts": source_counts,
            "sources": list(source_counts),
        },
        rejections=rejections,
    )
