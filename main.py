# ABOUTME: Defines the gskill CLI entry point.
# ABOUTME: Exposes commands for running the pipeline and previewing tasks.
"""gskill CLI entry point."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime

import typer

from src import tasks as task_bundle

app = typer.Typer(
    name="gskill",
    help="Automatically learn repository-specific skills for coding agents.",
    add_completion=False,
)


def _extract_repo_name(repo: str) -> str:
    """Extract an owner/repo slug from a repo identifier or GitHub URL."""
    value = repo.rstrip("/")
    if "github.com/" in value:
        parts = value.split("github.com/")[-1].split("/")
        return f"{parts[0]}/{parts[1]}"
    return value


@app.command()
def run(
    repo_url: str = typer.Argument(
        ..., help="GitHub repository URL, e.g. https://github.com/pallets/jinja"
    ),
    output_dir: str = typer.Option(
        ".claude/skills",
        "--output-dir",
        "-o",
        help="Directory to write the optimized SKILL.md.",
    ),
    max_evals: int = typer.Option(
        150,
        "--max-evals",
        "-n",
        help="GEPA evaluation budget (number of mini runs).",
    ),
    no_initial_skill: bool = typer.Option(
        False,
        "--no-initial-skill",
        help="Skip static analysis; start GEPA from an empty seed.",
    ),
    agent_model: str = typer.Option(
        "",
        "--agent-model",
        "-m",
        help="Model for mini-SWE-agent (e.g. openai/gpt-5.2). Env: GSKILL_AGENT_MODEL.",
    ),
    skill_model: str = typer.Option(
        "",
        "--skill-model",
        "-s",
        help="Model for initial skill generation (e.g. gpt-4o). Env: GSKILL_SKILL_MODEL.",
    ),
    base_url: str = typer.Option(
        "",
        "--base-url",
        "-u",
        help="OpenAI-compatible base URL for local models (e.g. http://localhost:11434/v1). Env: OPENAI_BASE_URL.",
    ),
    target_work_area: str = typer.Option(
        "",
        "--target-work-area",
        "-t",
        help=(
            "Optional GitHub repo URL or owner/repo string for the repository where the agent "
            "will continue working. SWE-smith tasks are loaded for this repo."
        ),
    ),
    seed_only: bool = typer.Option(
        False,
        "--seed-only",
        help="Generate and save a seed skill without SWE-smith tasks or GEPA optimization.",
    ),
    allow_missing_tasks: bool = typer.Option(
        False,
        "--allow-missing-tasks",
        help="If SWE-smith has no tasks for the repo, save the seed skill and exit successfully.",
    ),
    task_sources: list[str] | None = typer.Option(
        None,
        "--task-source",
        help=(
            "Named task source to use when building the optimization bundle. "
            "Repeat the flag to combine multiple sources. Defaults to the registered SWE-smith source. "
            "Registered sources include swe-smith, python-mutation, and python-history-replay."
        ),
    ),
    augment_suite: bool = typer.Option(
        True,
        "--augment-suite/--no-augment-suite",
        help=(
            "Generate companion skills in addition to the primary workflow skill. "
            "These companions capture reusable development capabilities from the source corpus."
        ),
    ),
    run_test_eval: bool = typer.Option(
        False,
        "--run-test-eval/--no-test-eval",
        help="Evaluate the best candidate on the holdout test split and save the summary to run-report.json.",
    ),
    test_eval_limit: int = typer.Option(
        0,
        "--test-eval-limit",
        help="Optional cap on the number of holdout test tasks to evaluate. 0 means use the full split.",
    ),
) -> None:
    """Run the gskill pipeline: optimize a SKILL.md for the given repository."""
    from src.pipeline import run as _run

    _run(
        repo_url=repo_url,
        output_dir=output_dir,
        max_evals=max_evals,
        use_initial_skill=not no_initial_skill,
        agent_model=agent_model or None,
        skill_model=skill_model or None,
        base_url=base_url or None,
        target_work_area=target_work_area or None,
        seed_only=seed_only,
        allow_missing_tasks=allow_missing_tasks,
        task_sources=task_sources or None,
        augment_suite=augment_suite,
        run_test_eval=run_test_eval,
        test_eval_limit=test_eval_limit or None,
    )


@app.command()
def tasks(
    repo: str = typer.Argument(
        ...,
        help="Repository name or GitHub URL, e.g. pallets/jinja or https://github.com/pallets/jinja",
    ),
    limit: int = typer.Option(
        10,
        "--limit",
        "-l",
        help="Maximum number of tasks to collect from each selected source.",
    ),
    list_all: bool = typer.Option(
        False,
        "--list",
        help="Print a concise summary of the selected tasks to stdout.",
    ),
    task_sources: list[str] | None = typer.Option(
        None,
        "--task-source",
        help=(
            "Named task source to use when building the preview bundle. "
            "Repeat the flag to combine multiple sources. Defaults to the registered SWE-smith source. "
            "Registered sources include swe-smith, python-mutation, and python-history-replay."
        ),
    ),
    checkout_path: str = typer.Option(
        "",
        "--checkout-path",
        help="Path to a local checkout for repo-native task sources.",
    ),
) -> None:
    """Preview canonical tasks for a repository and write them to a JSON file."""

    try:
        repo_name = _extract_repo_name(repo)
        repo_url = repo if "github.com" in repo else None
        bundle = task_bundle.build_task_bundle(
            repo_name=repo_name,
            repo_url=repo_url,
            checkout_path=checkout_path or None,
            source_names=task_sources or None,
            limit=limit,
        )
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)

    owner, short_repo_name = repo_name.split("/", 1)
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    filename = f"{short_repo_name}-{owner}--tasks-{timestamp}.json"

    with open(filename, "w") as f:
        json.dump(asdict(bundle), f, indent=2, default=str)

    if list_all:
        for task in bundle.tasks:
            typer.echo(f"{task.id} [{task.source}:{task.family}] {task.problem_statement}")

    typer.echo(
        f"Found {len(bundle.tasks)} canonical tasks for '{repo}' "
        f"({len(bundle.tasks)} written to {filename})"
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
