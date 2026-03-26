"""Mini-SWE-Agent evaluator for GEPA multi-task search."""

import os
import re
import shlex
import subprocess
import tempfile
import textwrap
import shutil
import warnings
from pathlib import Path
from typing import Callable

import gepa.optimize_anything as oa
import yaml
from minisweagent.agents import get_agent
from minisweagent.config import builtin_config_dir, get_config_from_spec
from minisweagent.models import get_model
from minisweagent.run.benchmarks.swebench import (
    get_sb_environment,
    get_swebench_docker_image_name,
)
from minisweagent.utils.serialize import recursive_merge

from .tasks import TaskSpec

_SWEBENCH_CONFIG = builtin_config_dir / "benchmarks" / "swebench.yaml"

# Base system prompt that frames the skill content
_SYSTEM_PREFIX = (
    "You are a helpful assistant that can interact with a computer shell "
    "to solve programming tasks.\n\n"
    "# Repository-Specific Knowledge\n\n"
)


def _log(message: str) -> None:
    """Log through GEPA without surfacing warnings in direct unit tests."""

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"oa\.log\(\) called outside of an evaluator function\..*",
            category=UserWarning,
        )
        oa.log(message)


def _write_skill_config(skill: str) -> Path:
    """Write a mini config YAML that overrides agent.system_template with the skill."""
    system_template = _SYSTEM_PREFIX + skill
    config = {"agent": {"system_template": system_template}}
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, prefix="gskill_skill_"
    )
    yaml.dump(config, tmp, default_flow_style=False, allow_unicode=True)
    tmp.close()
    return Path(tmp.name)


def _task_value(task: TaskSpec | dict, name: str, default: object = "") -> object:
    """Read a task field from either a canonical task or a raw task dict."""

    if isinstance(task, TaskSpec):
        return getattr(task, name, default)
    return task.get(name, default)


def _task_kind(spec: object) -> str:
    """Read a nested spec kind from dataclass or dict metadata."""

    if spec is None:
        return ""
    if isinstance(spec, dict):
        return str(spec.get("kind", ""))
    return str(getattr(spec, "kind", ""))


def _task_commands(spec: object) -> tuple[str, ...]:
    """Read a nested command list from dataclass or dict metadata."""

    if spec is None:
        return ()
    if isinstance(spec, dict):
        commands = spec.get("commands", ())
    else:
        commands = getattr(spec, "commands", ())
    if isinstance(commands, str):
        return (commands,)
    return tuple(str(command) for command in commands if str(command).strip())


def _task_snapshot_path(task: TaskSpec | dict) -> Path | None:
    """Return the repository snapshot path for a local-checkout task."""

    environment = _task_value(task, "environment", None)
    candidates: list[object] = []
    if isinstance(environment, dict):
        candidates.extend(
            environment.get(key)
            for key in (
                "ref",
                "snapshot_path",
                "checkout_path",
                "repo_path",
                "workspace_path",
            )
        )
    else:
        candidates.append(getattr(environment, "ref", ""))

    if isinstance(task, dict):
        candidates.extend(
            task.get(key)
            for key in (
                "ref",
                "snapshot_path",
                "checkout_path",
                "repo_path",
                "workspace_path",
            )
        )

    metadata = _task_value(task, "metadata", {})
    if isinstance(metadata, dict):
        candidates.extend(
            metadata.get(key)
            for key in (
                "snapshot_path",
                "checkout_path",
                "repo_path",
                "workspace_path",
            )
        )

    for candidate in candidates:
        if not candidate:
            continue
        path = Path(str(candidate)).expanduser()
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        return path
    return None


def _task_shell_verifier(task: TaskSpec | dict) -> list[str]:
    """Return the shell commands used to verify a local-checkout task."""

    verifier = _task_value(task, "verifier", None)
    commands = list(_task_commands(verifier))
    if commands:
        return commands

    if isinstance(task, dict):
        for key in ("verifier_command", "shell_command", "command"):
            value = task.get(key, "")
            if value:
                return [str(value)]
        value = task.get("commands", ())
        if isinstance(value, str):
            return [value]
        if isinstance(value, (list, tuple)):
            commands = [str(command) for command in value if str(command).strip()]
            if commands:
                return commands

    metadata = _task_value(task, "metadata", {})
    if isinstance(metadata, dict):
        for key in ("verifier_command", "shell_command", "command"):
            value = metadata.get(key, "")
            if value:
                return [str(value)]
        value = metadata.get("commands", ())
        if isinstance(value, str):
            return [value]
        if isinstance(value, (list, tuple)):
            return [str(command) for command in value if str(command).strip()]
    return []


def _task_local_checkout_instance(task: TaskSpec | dict) -> dict | None:
    """Return canonical metadata for a supported local-checkout task."""

    if isinstance(task, TaskSpec):
        if task.source == "swe-smith":
            return None
        if task.environment.kind != _LOCAL_CHECKOUT_ENV_KIND:
            return None
        if task.verifier.kind != _LOCAL_CHECKOUT_VERIFIER_KIND:
            return None
        snapshot_path = _task_snapshot_path(task)
        if snapshot_path is None:
            return None
        commands = _task_shell_verifier(task)
        if not commands:
            return None
        return {
            "instance_id": task.id,
            "problem_statement": task.problem_statement,
            "snapshot_path": snapshot_path,
            "verifier_commands": commands,
            "environment_timeout": task.environment.timeout_seconds,
            "verifier_timeout": task.verifier.timeout_seconds,
            "metadata": dict(task.metadata),
        }

    environment = task.get("environment")
    verifier = task.get("verifier")
    if isinstance(environment, dict) and isinstance(verifier, dict):
        if _task_kind(environment) != _LOCAL_CHECKOUT_ENV_KIND:
            return None
        if _task_kind(verifier) != _LOCAL_CHECKOUT_VERIFIER_KIND:
            return None
        snapshot_path = _task_snapshot_path(task)
        commands = _task_shell_verifier(task)
        if snapshot_path is None or not commands:
            return None
        return {
            "instance_id": str(task.get("instance_id", "unknown")),
            "problem_statement": str(task.get("problem_statement", "")),
            "snapshot_path": snapshot_path,
            "verifier_commands": commands,
            "environment_timeout": environment.get("timeout_seconds"),
            "verifier_timeout": verifier.get("timeout_seconds"),
            "metadata": dict(task.get("metadata", {})),
        }

    if any(
        task.get(key)
        for key in (
            "snapshot_path",
            "checkout_path",
            "repo_path",
            "workspace_path",
            "verifier_command",
            "shell_command",
            "command",
            "commands",
        )
    ):
        snapshot_path = _task_snapshot_path(task)
        commands = _task_shell_verifier(task)
        if snapshot_path is None or not commands:
            return None
        return {
            "instance_id": str(task.get("instance_id", "unknown")),
            "problem_statement": str(task.get("problem_statement", "")),
            "snapshot_path": snapshot_path,
            "verifier_commands": commands,
            "environment_timeout": task.get("environment_timeout_seconds"),
            "verifier_timeout": task.get("verifier_timeout_seconds"),
            "metadata": dict(task.get("metadata", {})),
        }

    if _task_kind(environment) == _LOCAL_CHECKOUT_ENV_KIND:
        snapshot_path = _task_snapshot_path(task)
        commands = _task_shell_verifier(task)
        if snapshot_path is None or not commands:
            return None
        return {
            "instance_id": str(task.get("instance_id", "unknown")),
            "problem_statement": str(task.get("problem_statement", "")),
            "snapshot_path": snapshot_path,
            "verifier_commands": commands,
            "environment_timeout": task.get("environment_timeout_seconds"),
            "verifier_timeout": task.get("verifier_timeout_seconds"),
            "metadata": dict(task.get("metadata", {})),
        }

    return None


def _build_test_command(instance: dict, max_tests: int = 10) -> tuple[str, str]:
    """Build a repo-aware test command from SWE-smith task metadata."""
    fail_to_pass: list[str] = instance.get("FAIL_TO_PASS", [])[:max_tests]
    if not fail_to_pass:
        return "", "no_tests"

    repo_hint = " ".join(
        str(instance.get(key, "")) for key in ("repo", "image_name", "instance_id")
    ).lower()
    quoted_ids = " ".join(shlex.quote(test_id) for test_id in fail_to_pass)

    if any(".py::" in test_id or test_id.endswith(".py") for test_id in fail_to_pass):
        return f"python -m pytest {quoted_ids} -x --tb=no -q 2>&1", "pytest"

    if all(re.fullmatch(r"(Test|Example|Benchmark)[A-Za-z0-9_]+", test_id) for test_id in fail_to_pass):
        pattern = "|".join(re.escape(test_id) for test_id in fail_to_pass)
        return (
            f"go test ./... -run '^{pattern}$' -count=1 2>&1",
            "go_test",
        )

    if "cargo" in repo_hint or "rust" in repo_hint:
        return (
            f"cargo test {' '.join(shlex.quote(test_id) for test_id in fail_to_pass)} -- --nocapture 2>&1",
            "cargo_test",
        )

    adaptive = textwrap.dedent(
        f"""\
        if [ -f go.mod ]; then
            go test ./... -count=1 2>&1
        elif [ -f Cargo.toml ]; then
            cargo test -- --nocapture 2>&1
        elif [ -f package.json ]; then
            npm test -- --runInBand 2>&1 || npm test 2>&1
        else
            python -m pytest {quoted_ids} -x --tb=no -q 2>&1
        fi
        """
    ).strip()
    return adaptive, "adaptive"


def _run_shell_script(
    command: str,
    *,
    cwd: Path,
    timeout: int,
    label: str,
) -> tuple[bool, subprocess.CompletedProcess[str] | None, str]:
    """Run a shell script in a working directory and return success plus output."""

    try:
        result = subprocess.run(
            ["bash", "-lc", command],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, None, f"{label}_timeout"
    except FileNotFoundError:
        return False, None, f"{label}_shell_not_found"

    passed = result.returncode == 0
    if not passed:
        stdout_tail = result.stdout[-500:] if result.stdout else ""
        stderr_tail = result.stderr[-500:] if result.stderr else ""
        _log(
            f"{label} failed exit={result.returncode} cwd={cwd} "
            f"stdout={stdout_tail!r} stderr={stderr_tail!r}"
        )
    return passed, result, f"{label}_passed" if passed else f"{label}_failed"


def _task_submission_patch(task_dir: Path | None, result: object) -> str:
    """Extract or synthesize the patch produced by the agent."""

    if isinstance(result, dict):
        for key in ("submission", "patch", "diff"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return value
        if isinstance(result.get("submission"), tuple):
            submission = result["submission"]
            if submission and isinstance(submission[0], str):
                return submission[0]
    elif isinstance(result, tuple):
        if result and isinstance(result[0], str) and result[0].strip():
            return result[0]
    elif isinstance(result, str) and result.strip():
        return result

    if task_dir is not None:
        try:
            diff = subprocess.run(
                ["git", "-C", str(task_dir), "diff", "--binary", "--no-ext-diff", "--"],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            return ""
        if diff.returncode == 0 and diff.stdout.strip():
            return diff.stdout
    return ""


def _run_local_checkout_verifier(
    snapshot_path: Path,
    patch: str,
    verifier_commands: list[str],
    timeout: int,
) -> tuple[bool, str]:
    """Verify a local-checkout task in a fresh copy of the snapshot."""

    if not verifier_commands:
        return False, "no_shell_command"

    verify_dir = Path(tempfile.mkdtemp(prefix="gskill_verify_"))
    try:
        shutil.copytree(snapshot_path, verify_dir, dirs_exist_ok=True)
    except Exception as exc:
        _log(f"Could not copy snapshot for verification: {type(exc).__name__}: {exc}")
        return False, "snapshot_copy_failed"

    patch_file = None
    try:
        if patch.strip():
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".patch", delete=False, prefix="gskill_patch_"
            ) as f:
                f.write(patch)
                patch_file = Path(f.name)
            apply_script = textwrap.dedent(
                f"""\
                git apply {shlex.quote(str(patch_file))} 2>/dev/null || patch -p1 < {shlex.quote(str(patch_file))} 2>/dev/null
                """
            ).strip()
            applied, _, apply_reason = _run_shell_script(
                apply_script,
                cwd=verify_dir,
                timeout=timeout,
                label="patch_apply",
            )
            if not applied:
                return False, apply_reason

        verifier_script = "set -euo pipefail\n" + "\n".join(verifier_commands)
        passed, result, reason = _run_shell_script(
            verifier_script,
            cwd=verify_dir,
            timeout=timeout,
            label="shell_command",
        )
        if result is not None:
            stdout_tail = result.stdout[-500:] if result.stdout else ""
            _log(f"Verifier stdout tail: {stdout_tail}")
        return passed, reason
    finally:
        if patch_file is not None:
            try:
                os.unlink(patch_file)
            except OSError:
                pass
        shutil.rmtree(verify_dir, ignore_errors=True)


def _cleanup_environment(env: object | None) -> None:
    """Best-effort cleanup for mini-swe-agent environments."""

    if env is None:
        return
    cleanup = getattr(env, "cleanup", None)
    if callable(cleanup):
        cleanup()


def _run_tests(instance: dict, patch: str) -> tuple[bool, str]:
    """Apply the agent's patch and run FAIL_TO_PASS tests in a fresh Docker container.

    Args:
        instance: SWE-smith task dict (must have FAIL_TO_PASS; image resolved via
            get_swebench_docker_image_name, which checks image_name / docker_image
            and falls back to constructing from instance_id).
        patch: Git diff patch string produced by the agent.

    Returns:
        Tuple of (passed, reason) where reason describes the outcome.
    """
    fail_to_pass: list[str] = instance.get("FAIL_TO_PASS", [])
    if not fail_to_pass:
        _log("No FAIL_TO_PASS tests found, skipping test run")
        return False, "no_fail_to_pass_tests"

    image_name = get_swebench_docker_image_name(instance)
    _log(f"Test container image: {image_name}")

    test_command, test_mode = _build_test_command(instance)
    if not test_command:
        _log("No runnable test command could be inferred from FAIL_TO_PASS metadata")
        return False, "no_test_command"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".patch", delete=False) as f:
        f.write(patch)
        patch_file = f.name

    test_cmd = textwrap.dedent(f"""\
        cd /testbed
        git apply /tmp/solution.patch 2>/dev/null || patch -p1 < /tmp/solution.patch 2>/dev/null
        {test_command}
    """)

    try:
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{patch_file}:/tmp/solution.patch:ro",
                image_name,
                "bash",
                "-c",
                test_cmd,
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )
        passed = result.returncode == 0
        stdout_tail = result.stdout[-500:] if result.stdout else ""
        _log(f"Test stdout tail: {stdout_tail}")
        if not passed:
            _log(
                f"Tests failed (exit {result.returncode}) mode={test_mode} for image={image_name}; "
                f"stderr: {result.stderr[-200:] if result.stderr else '(none)'}"
            )
        return passed, f"{test_mode}_passed" if passed else f"{test_mode}_failed"
    except subprocess.TimeoutExpired:
        _log(f"Test run timed out (180s) for image={image_name}")
        return False, f"{test_mode}_timeout"
    except FileNotFoundError:
        _log(
            "Docker executable not found; ensure Docker is installed and running. "
            "All evaluations will score 0.0 until Docker is available."
        )
        return False, "docker_not_found"
    finally:
        os.unlink(patch_file)


def _task_instance_id(task: TaskSpec | dict) -> str:
    """Return a stable task identifier for logging and reports."""

    if isinstance(task, TaskSpec):
        return task.id
    return task.get("instance_id", "unknown")


def _task_problem_statement(task: TaskSpec | dict) -> str:
    """Return the problem statement regardless of task representation."""

    if isinstance(task, TaskSpec):
        return task.problem_statement
    return task["problem_statement"]


def _task_to_swebench_instance(task: TaskSpec | dict) -> dict | None:
    """Return raw SWE-bench-style metadata for supported canonical tasks."""

    if isinstance(task, TaskSpec):
        if task.environment.kind != "swebench_docker" or task.verifier.kind != "test_selectors":
            return None
        if task.source != "swe-smith":
            return None
        return dict(task.metadata)

    environment = task.get("environment")
    verifier = task.get("verifier")
    source = str(task.get("source", ""))
    if isinstance(environment, dict) and isinstance(verifier, dict):
        if _task_kind(environment) != "swebench_docker" or _task_kind(verifier) != "test_selectors":
            return None
        if source != "swe-smith":
            return None
        metadata = task.get("metadata", {})
        if isinstance(metadata, dict) and metadata:
            return dict(metadata)
        return dict(task)
    if any(
        task.get(key)
        for key in (
            "snapshot_path",
            "checkout_path",
            "repo_path",
            "workspace_path",
            "verifier_command",
            "shell_command",
            "command",
            "commands",
        )
    ):
        return None
    if "FAIL_TO_PASS" in task and "problem_statement" in task:
        return dict(task)
    return None


def _task_to_local_checkout(task: TaskSpec | dict) -> dict | None:
    """Return canonical metadata for supported local-checkout tasks."""

    local_task = _task_local_checkout_instance(task)
    if local_task is None:
        return None
    return local_task


def _task_runner_kind(task: TaskSpec | dict) -> str:
    """Select the evaluator path for a canonical task."""

    if _task_to_local_checkout(task) is not None:
        return "local_checkout"
    if _task_to_swebench_instance(task) is not None:
        return "swebench"
    return "unsupported"


def make_evaluator(
    agent_model: str | None = None,
) -> Callable[[str, TaskSpec | dict], tuple[float, dict]]:
    """Create a GEPA-compatible evaluator that runs mini-SWE-Agent on a SWE-smith task.

    The returned evaluator:
      1. Writes the candidate skill into a temporary mini config YAML.
      2. Runs mini's Python API (swebench mode) on the task in Docker.
      3. Extracts the submitted patch from the agent's trajectory.
      4. Verifies the patch by running FAIL_TO_PASS tests in a fresh container.
      5. Returns (score, side_info) for GEPA reflection.

    Args:
        agent_model: LiteLLM model string for mini-SWE-agent (e.g. ``openai/gpt-5.2``).
            Falls back to the ``GSKILL_AGENT_MODEL`` env var, then ``openai/gpt-5.2``.

    Returns:
        Callable suitable for passing to ``optimize_anything(evaluator=...)``.
    """
    resolved_model = agent_model or os.environ.get(
        "GSKILL_AGENT_MODEL", "openai/gpt-5.2"
    )

    def evaluate(candidate_skill: str, task: TaskSpec | dict) -> tuple[float, dict]:
        instance_id = _task_instance_id(task)
        skill_config_path = _write_skill_config(candidate_skill)
        traj_tmp = tempfile.NamedTemporaryFile(
            suffix=".traj.json", delete=False, prefix="gskill_traj_"
        )
        traj_tmp.close()

        patch = ""
        score = 0.0
        error_msg = ""
        test_reason = ""
        env = None
        working_copy: Path | None = None
        runner_kind = _task_runner_kind(task)

        if runner_kind == "unsupported":
            _log(f"instance={instance_id} unsupported runner for canonical task")
            try:
                os.unlink(skill_config_path)
            except OSError:
                pass
            try:
                os.unlink(traj_tmp.name)
            except OSError:
                pass
            return 0.0, {
                "instance_id": instance_id,
                "patch_chars": 0,
                "score": 0.0,
                "error": "",
                "test_failure_reason": "unsupported_runner",
            }

        try:
            if runner_kind == "swebench":
                instance = _task_to_swebench_instance(task)
                if instance is None:
                    raise ValueError("swebench task metadata missing")
                configs = [
                    get_config_from_spec(str(_SWEBENCH_CONFIG)),
                    get_config_from_spec(str(skill_config_path)),
                    {"agent": {"output_path": traj_tmp.name}},
                    {"model": {"model_name": resolved_model}},
                ]
                config = recursive_merge(*configs)

                env = get_sb_environment(config, instance)
                model = get_model(config=config.get("model", {}))
                agent = get_agent(
                    model, env, config.get("agent", {}), default_type="default"
                )

                result = agent.run(_task_problem_statement(task))
                patch = _task_submission_patch(None, result)
            else:
                instance = _task_to_local_checkout(task)
                if instance is None:
                    raise ValueError("local checkout task metadata missing")
                snapshot_path = instance["snapshot_path"]
                if not isinstance(snapshot_path, Path):
                    snapshot_path = Path(str(snapshot_path))
                if not snapshot_path.exists():
                    raise FileNotFoundError(f"Snapshot path does not exist: {snapshot_path}")
                working_copy = Path(tempfile.mkdtemp(prefix="gskill_local_"))
                shutil.copytree(snapshot_path, working_copy, dirs_exist_ok=True)

                configs = [
                    get_config_from_spec(str(builtin_config_dir / "mini.yaml")),
                    get_config_from_spec(str(skill_config_path)),
                    {"agent": {"output_path": traj_tmp.name}},
                    {"model": {"model_name": resolved_model}},
                    {"environment": {"cwd": str(working_copy)}},
                ]
                config = recursive_merge(*configs)

                env = get_environment(config.get("environment", {}), default_type="local")
                model = get_model(config=config.get("model", {}))
                agent = get_agent(
                    model, env, config.get("agent", {}), default_type="default"
                )

                result = agent.run(_task_problem_statement(task))
                patch = _task_submission_patch(working_copy, result)
                if patch.strip():
                    timeout = int(
                        instance.get("verifier_timeout")
                        or instance.get("environment_timeout")
                        or 180
                    )
                    passed, test_reason = _run_local_checkout_verifier(
                        snapshot_path,
                        patch,
                        instance["verifier_commands"],
                        timeout,
                    )
                    score = 1.0 if passed else 0.0
                    _log(
                        f"instance={instance_id} patch={len(patch)}chars "
                        f"tests={'passed' if passed else 'failed'} reason={test_reason} score={score}"
                    )
                else:
                    test_reason = "no_patch_submitted"
                    _log(
                        f"instance={instance_id} no patch submitted score=0.0"
                        + (f"; agent error: {error_msg}" if error_msg else "")
                    )

        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            _log(f"Mini run error: {error_msg}")
        finally:
            _cleanup_environment(env)
            if working_copy is not None:
                shutil.rmtree(working_copy, ignore_errors=True)
            for path in (skill_config_path, traj_tmp.name):
                try:
                    os.unlink(path)
                except OSError:
                    pass

        if runner_kind == "swebench" and patch.strip():
            instance = _task_to_swebench_instance(task)
            if instance is not None:
                passed, test_reason = _run_tests(instance, patch)
                score = 1.0 if passed else 0.0
                _log(
                    f"instance={instance_id} patch={len(patch)}chars "
                    f"tests={'passed' if passed else 'failed'} reason={test_reason} score={score}"
                )
        elif runner_kind == "swebench" and not patch.strip():
            test_reason = "no_patch_submitted"
            _log(
                f"instance={instance_id} no patch submitted score=0.0"
                + (f"; agent error: {error_msg}" if error_msg else "")
            )

        return score, {
            "instance_id": instance_id,
            "patch_chars": len(patch),
            "score": score,
            "error": error_msg,
            "test_failure_reason": test_reason,
        }

    return evaluate
