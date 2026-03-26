"""Task loading, canonical task models, and bundle assembly for gskill."""

from __future__ import annotations

import ast
import hashlib
import shlex
import shutil
import subprocess
import tempfile
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from datasets import load_dataset

DATASET_NAME = "SWE-bench/SWE-smith"
DEFAULT_TASK_SOURCE = "swe-smith"
PYTHON_MUTATION_TASK_SOURCE = "python-mutation"
DEFAULT_COMMAND_TIMEOUT = 120


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


@dataclass(frozen=True)
class TaskSourceRequest:
    """Request context passed to each task source."""

    repo_name: str
    repo_url: str | None = None
    checkout_path: str | None = None
    limit: int = 300
    scratch_dir: str | None = None


@dataclass(frozen=True)
class PythonMutationCandidate:
    """A reversible Python mutation extracted from a source file."""

    relative_path: str
    start: int
    end: int
    replacement: str
    original: str
    description: str
    line: int


class TaskSource(Protocol):
    """Collect tasks for a repository from a named source."""

    name: str

    def collect(self, request: TaskSourceRequest | str, limit: int = 300) -> list[TaskSpec]:
        """Return canonical tasks for the given repository."""


def _repo_slug(repo_name: str) -> str:
    """Normalize a repo slug for dataset matching and path naming."""

    return repo_name.replace("/", "__")


def _filter_swe_smith_records(repo_name: str, n: int = 300) -> list[dict[str, Any]]:
    """Load raw SWE-smith records filtered by repo_name."""

    ds = load_dataset(DATASET_NAME, split="train")
    slug = _repo_slug(repo_name)
    records = [dict(row) for row in ds if slug in row["repo"]]
    if not records:
        raise ValueError(
            f"No tasks found for repo '{repo_name}' in {DATASET_NAME}. "
            f"Use the full 'owner/repo' format, e.g., 'pallets/jinja'."
        )
    return records[:n]


def _ensure_scratch_dir(request: TaskSourceRequest) -> Path:
    """Return the scratch directory for source materialization."""

    if request.scratch_dir:
        root = Path(request.scratch_dir)
        root.mkdir(parents=True, exist_ok=True)
        return root
    return Path(tempfile.mkdtemp(prefix="gskill-task-source-"))


def _run_shell_command(command: str, cwd: Path, timeout: int = DEFAULT_COMMAND_TIMEOUT) -> subprocess.CompletedProcess:
    """Run a shell command for task validation or repo preparation."""

    return subprocess.run(
        command,
        shell=True,
        text=True,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
    )


def _materialize_repo_checkout(request: TaskSourceRequest) -> Path:
    """Materialize the repository checkout used by repo-native sources."""

    if request.checkout_path:
        checkout_path = Path(request.checkout_path).resolve()
        if not checkout_path.exists():
            raise ValueError(f"Checkout path does not exist: {checkout_path}")
        return checkout_path

    if request.repo_url:
        repo_url = request.repo_url
        local_path = Path(repo_url).expanduser()
        if "://" not in repo_url and local_path.exists():
            return local_path.resolve()

        scratch_root = _ensure_scratch_dir(request)
        repo_root = scratch_root / f"{_repo_slug(request.repo_name)}-source"
        if repo_root.exists():
            return repo_root
        result = _run_shell_command(
            f"git clone --depth 1 {repo_url} {repo_root}",
            cwd=scratch_root,
            timeout=DEFAULT_COMMAND_TIMEOUT,
        )
        if result.returncode != 0:
            raise ValueError(f"Could not clone repository for mutation tasks: {result.stdout.strip()}")
        return repo_root

    raise ValueError(
        f"Task source '{PYTHON_MUTATION_TASK_SOURCE}' requires a repo URL or checkout path for {request.repo_name}."
    )


def _discover_python_verifier_command(repo_root: Path) -> str:
    """Infer a repository-wide Python verification command."""

    has_tests = (repo_root / "tests").exists() or any(repo_root.glob("test_*.py"))
    has_pytest_config = any(
        (repo_root / name).exists() for name in ("pytest.ini", "setup.cfg")
    )
    venv_python = repo_root / ".venv" / "bin" / "python"
    interpreter = venv_python if venv_python.exists() else Path(sys.executable)
    python_command = f"{shlex.quote(str(interpreter))} -m pytest -q"
    if (repo_root / "noxfile.py").exists():
        return "uv run nox -s tests"
    if (repo_root / "tox.ini").exists():
        return "uv run tox"
    if has_tests or has_pytest_config or (repo_root / "pyproject.toml").exists():
        return python_command
    raise ValueError(
        f"Could not infer a Python verifier command for {repo_root}. No tests or pytest config found."
    )


def _python_source_files(repo_root: Path) -> list[Path]:
    """Return Python implementation files that are reasonable mutation candidates."""

    files: list[Path] = []
    excluded_prefixes = {".git", ".venv", "__pycache__", "tests", "bootstrap"}
    for path in repo_root.rglob("*.py"):
        relative_parts = set(path.relative_to(repo_root).parts)
        if excluded_prefixes & relative_parts:
            continue
        files.append(path)
    return sorted(files)


def _slice_offsets(source: str, node: ast.AST) -> tuple[int, int]:
    """Convert AST line/column locations into absolute character offsets."""

    lines = source.splitlines(keepends=True)

    def line_offset(line_number: int, column: int) -> int:
        return sum(len(line) for line in lines[: line_number - 1]) + column

    start = line_offset(node.lineno, node.col_offset)
    end = line_offset(node.end_lineno, node.end_col_offset)
    return start, end


def _candidate_for_compare(source: str, relative_path: str, node: ast.Compare) -> PythonMutationCandidate | None:
    """Build a mutation candidate from a simple compare operator."""

    if len(node.ops) != 1:
        return None
    operator = node.ops[0]
    replacements = {
        ast.Eq: "!=",
        ast.NotEq: "==",
        ast.Gt: ">=",
        ast.GtE: ">",
        ast.Lt: "<=",
        ast.LtE: "<",
        ast.Is: "is not",
        ast.IsNot: "is",
        ast.In: "not in",
        ast.NotIn: "in",
    }
    replacement = replacements.get(type(operator))
    if replacement is None:
        return None
    _, left_end = _slice_offsets(source, node.left)
    right_start, _ = _slice_offsets(source, node.comparators[0])
    original = source[left_end:right_start]
    if not original.strip():
        return None
    return PythonMutationCandidate(
        relative_path=relative_path,
        start=left_end,
        end=right_start,
        replacement=replacement,
        original=original,
        description=f"Replace '{original}' with '{replacement}'",
        line=node.lineno,
    )


def _candidate_for_constant(source: str, relative_path: str, node: ast.Constant) -> PythonMutationCandidate | None:
    """Build a mutation candidate from a boolean constant."""

    if not isinstance(node.value, bool):
        return None
    start, end = _slice_offsets(source, node)
    original = source[start:end]
    replacement = "False" if node.value else "True"
    return PythonMutationCandidate(
        relative_path=relative_path,
        start=start,
        end=end,
        replacement=replacement,
        original=original,
        description=f"Replace '{original}' with '{replacement}'",
        line=node.lineno,
    )


def _python_mutation_candidates(repo_root: Path) -> list[PythonMutationCandidate]:
    """Extract a small set of safe, reversible mutation candidates from Python files."""

    candidates: list[PythonMutationCandidate] = []
    for source_file in _python_source_files(repo_root):
        source = source_file.read_text()
        relative_path = str(source_file.relative_to(repo_root))
        tree = ast.parse(source)
        for node in ast.walk(tree):
            candidate: PythonMutationCandidate | None = None
            if isinstance(node, ast.Compare):
                candidate = _candidate_for_compare(source, relative_path, node)
            elif isinstance(node, ast.Constant):
                candidate = _candidate_for_constant(source, relative_path, node)
            if candidate is not None:
                candidates.append(candidate)
    return candidates


def _apply_python_mutation(repo_root: Path, candidate: PythonMutationCandidate) -> None:
    """Apply a mutation candidate to a checkout snapshot."""

    target_file = repo_root / candidate.relative_path
    source = target_file.read_text()
    mutated = source[: candidate.start] + candidate.replacement + source[candidate.end :]
    target_file.write_text(mutated)


def _task_snapshot_root(request: TaskSourceRequest, scratch_root: Path) -> Path:
    """Return the directory where accepted mutation snapshots are stored."""

    snapshot_root = scratch_root / f"{_repo_slug(request.repo_name)}-mutation-snapshots"
    snapshot_root.mkdir(parents=True, exist_ok=True)
    return snapshot_root


def _copy_checkout(repo_root: Path, destination: Path) -> Path:
    """Copy a repository checkout to a destination path."""

    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(repo_root, destination)
    return destination


def _mutation_task_id(request: TaskSourceRequest, candidate: PythonMutationCandidate) -> str:
    """Create a stable task id for a mutation candidate."""

    fingerprint = hashlib.sha1(
        f"{request.repo_name}:{candidate.relative_path}:{candidate.line}:{candidate.description}".encode()
    ).hexdigest()[:10]
    return f"python-mutation-{fingerprint}"


class SweSmithSource:
    """Canonical task adapter for the SWE-smith dataset."""

    name = DEFAULT_TASK_SOURCE

    def collect(self, request: TaskSourceRequest | str, limit: int = 300) -> list[TaskSpec]:
        repo_name = request.repo_name if isinstance(request, TaskSourceRequest) else request
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


class PythonMutationSource:
    """Collect repo-native Python mutation tasks from a repository checkout."""

    name = PYTHON_MUTATION_TASK_SOURCE

    def collect(self, request: TaskSourceRequest | str, limit: int = 300) -> list[TaskSpec]:
        if isinstance(request, str):
            request = TaskSourceRequest(repo_name=request, limit=limit)
        repo_root = _materialize_repo_checkout(request)
        verifier_command = _discover_python_verifier_command(repo_root)
        baseline = _run_shell_command(verifier_command, cwd=repo_root)
        if baseline.returncode != 0:
            raise ValueError(
                f"Baseline verifier failed for {request.repo_name} with '{verifier_command}': "
                f"{baseline.stdout.strip()}"
            )

        candidates = _python_mutation_candidates(repo_root)
        if not candidates:
            raise ValueError(f"No Python mutation candidates found for {request.repo_name}.")

        scratch_root = _ensure_scratch_dir(request)
        snapshot_root = _task_snapshot_root(request, scratch_root)
        accepted: list[TaskSpec] = []

        for index, candidate in enumerate(candidates):
            if len(accepted) >= request.limit:
                break
            checkout_copy = _copy_checkout(repo_root, snapshot_root / f"candidate-{index}")
            _apply_python_mutation(checkout_copy, candidate)
            result = _run_shell_command(verifier_command, cwd=checkout_copy)
            if result.returncode == 0:
                shutil.rmtree(checkout_copy)
                continue

            task_id = _mutation_task_id(request, candidate)
            accepted.append(
                TaskSpec(
                    id=task_id,
                    family="mutation",
                    source=PYTHON_MUTATION_TASK_SOURCE,
                    repo_name=request.repo_name,
                    problem_statement=(
                        f"A regression was introduced in '{candidate.relative_path}' near line {candidate.line}. "
                        f"Restore repository behavior without editing tests. "
                        f"Validate the fix with `{verifier_command}`."
                    ),
                    environment=EnvironmentSpec(
                        kind="local_checkout",
                        ref=str(checkout_copy),
                        timeout_seconds=DEFAULT_COMMAND_TIMEOUT,
                    ),
                    verifier=VerifierSpec(
                        kind="shell_command",
                        commands=(verifier_command,),
                        timeout_seconds=DEFAULT_COMMAND_TIMEOUT,
                    ),
                    metadata={
                        "repo_url": request.repo_url,
                        "mutation": {
                            "description": candidate.description,
                            "line": candidate.line,
                            "path": candidate.relative_path,
                            "original": candidate.original,
                            "replacement": candidate.replacement,
                        },
                        "verifier_output_tail": result.stdout[-500:],
                    },
                    mutable_paths=(candidate.relative_path,),
                )
            )

        if not accepted:
            raise ValueError(
                f"Could not generate validated Python mutation tasks for {request.repo_name} using '{verifier_command}'."
            )
        return accepted


_TASK_SOURCES: dict[str, TaskSource] = {
    DEFAULT_TASK_SOURCE: SweSmithSource(),
    PYTHON_MUTATION_TASK_SOURCE: PythonMutationSource(),
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
    repo_url: str | None = None,
    checkout_path: str | None = None,
    source_names: list[str] | None = None,
    limit: int = 300,
    train: float = 0.67,
    val: float = 0.17,
    scratch_dir: str | None = None,
) -> TaskBundle:
    """Collect tasks from named sources and assemble a canonical bundle."""

    selected_sources = source_names or [DEFAULT_TASK_SOURCE]
    collected: list[TaskSpec] = []
    source_counts: dict[str, int] = {}
    rejections: list[dict[str, Any]] = []

    for source_name in selected_sources:
        source = get_task_source(source_name)
        request = TaskSourceRequest(
            repo_name=repo_name,
            repo_url=repo_url,
            checkout_path=checkout_path,
            limit=limit,
            scratch_dir=scratch_dir,
        )
        try:
            if source_name == DEFAULT_TASK_SOURCE:
                source_tasks = source.collect(repo_name, limit)
            else:
                source_tasks = source.collect(request, limit)
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
            "repo_url": repo_url,
            "checkout_path": checkout_path,
        },
        rejections=rejections,
    )
