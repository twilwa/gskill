"""Top-level pipeline orchestration for gskill."""

from inspect import signature
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Callable

from gepa.optimize_anything import EngineConfig, GEPAConfig, optimize_anything

from .evaluator import make_evaluator
from .skill import (
    SkillArtifact,
    SkillSuite,
    _artifact_from_content,
    augment_skill_suite,
    generate_initial_skill_suite,
    save_skill_suite,
)
from . import tasks as task_models
from .tasks import DEFAULT_TASK_SOURCE, build_task_bundle


def _extract_repo_name(repo_url: str) -> str:
    """Extract 'owner/repo' from a GitHub URL or pass-through if already in that form."""
    url = repo_url.rstrip("/")
    if "github.com" in url:
        parts = url.split("github.com/")[-1].split("/")
        return f"{parts[0]}/{parts[1]}"
    # Assume already "owner/repo" or "repo"
    return url


def _make_task_bundle_request(
    repo_name: str,
    repo_url: str,
    limit: int,
    scratch_dir: Path,
) -> object:
    """Build the task-source request object expected by repo-native sources."""
    payload = {
        "repo_name": repo_name,
        "repo_url": repo_url,
        "limit": limit,
        "scratch_dir": str(scratch_dir),
    }
    request_type = getattr(task_models, "TaskSourceRequest", None)
    if request_type is None:
        return SimpleNamespace(**payload)

    try:
        request_params = signature(request_type).parameters
    except (TypeError, ValueError):
        request_params = {}
    if request_params:
        filtered_payload = {
            key: value for key, value in payload.items() if key in request_params
        }
        return request_type(**filtered_payload)
    return request_type(**payload)


def _build_task_bundle(
    repo_name: str,
    repo_url: str,
    source_names: list[str] | None,
    limit: int,
    scratch_dir: Path,
) -> tuple[object, object, list[str]]:
    """Call the task bundle builder with either the old or request-based interface."""
    selected_sources = source_names or [DEFAULT_TASK_SOURCE]
    request = _make_task_bundle_request(repo_name, repo_url, limit, scratch_dir)

    try:
        parameters = signature(build_task_bundle).parameters
    except (TypeError, ValueError):
        parameters = {}

    if "request" in parameters:
        kwargs: dict[str, object] = {"request": request}
        if "source_names" in parameters:
            kwargs["source_names"] = selected_sources
        bundle = build_task_bundle(**kwargs)
        return bundle, request, selected_sources

    if "task_source_request" in parameters:
        kwargs = {"task_source_request": request}
        if "source_names" in parameters:
            kwargs["source_names"] = selected_sources
        bundle = build_task_bundle(**kwargs)
        return bundle, request, selected_sources

    kwargs: dict[str, object] = {
        "repo_name": repo_name,
        "source_names": selected_sources,
    }
    if "limit" in parameters:
        kwargs["limit"] = limit
    bundle = build_task_bundle(**kwargs)
    return bundle, request, selected_sources


def evaluate_holdout(
    evaluator: Callable[[str, dict], tuple[float, dict]],
    candidate_skill: str,
    tasks: list[dict],
    limit: int | None = None,
) -> dict:
    """Evaluate a candidate skill on a holdout split and summarize outcomes."""
    selected = tasks[:limit] if limit is not None else tasks
    results: list[dict] = []
    passed = 0
    for task in selected:
        score, info = evaluator(candidate_skill, task)
        if score >= 1.0:
            passed += 1
        results.append(info)

    attempted = len(selected)
    return {
        "attempted": attempted,
        "passed": passed,
        "score": (passed / attempted) if attempted else None,
        "instances": [task.get("instance_id", "unknown") for task in selected],
        "results": results,
    }


def save_run_report(report: dict, repo_name: str, output_dir: str = ".claude/skills") -> Path:
    """Persist run metadata next to the generated skill suite."""
    short_name = repo_name.split("/")[-1]
    path = Path(output_dir) / short_name / "run-report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2))
    return path


def run(
    repo_url: str,
    output_dir: str = ".claude/skills",
    max_evals: int = 150,
    use_initial_skill: bool = True,
    agent_model: str | None = None,
    skill_model: str | None = None,
    base_url: str | None = None,
    target_work_area: str | None = None,
    seed_only: bool = False,
    allow_missing_tasks: bool = False,
    task_sources: list[str] | None = None,
    augment_suite: bool = True,
    run_test_eval: bool = False,
    test_eval_limit: int | None = None,
) -> object:
    """Run the full gskill pipeline for a repository.

    Args:
        repo_url: GitHub repository URL (e.g., 'https://github.com/pallets/jinja').
        output_dir: Directory to write the optimized SKILL.md.
        max_evals: GEPA evaluation budget (number of mini runs).
        use_initial_skill: If True, generate an initial skill as the seed.
            If False, start GEPA from an empty seed.
        agent_model: LiteLLM model string for mini-SWE-agent. Falls back to
            ``GSKILL_AGENT_MODEL`` env var, then ``openai/gpt-5.2``.
        skill_model: Model for initial skill generation. Falls back to
            ``GSKILL_SKILL_MODEL`` env var, then ``gpt-5.2``.
        base_url: OpenAI-compatible base URL for local models. Falls back to
            ``OPENAI_BASE_URL`` env var.
        target_work_area: Optional repository URL or ``owner/repo`` string for
            the place where the agent will continue working. Defaults to
            ``repo_url``. SWE-smith tasks are loaded for this repo.
        seed_only: If True, only generate and save the initial skill suite.
        allow_missing_tasks: If True, save the seed skill and exit when the
            repository is not present in SWE-smith.
        task_sources: Optional named task sources to use when building the
            optimization bundle. Defaults to the registered SWE-smith source.
        augment_suite: If True, generate companion skills after the primary
            workflow skill is seeded or optimized.
        run_test_eval: If True, evaluate the best candidate on the holdout test split.
        test_eval_limit: Optional limit for holdout evaluations.

    Returns:
        GEPA result object with ``best_candidate`` and ``best_score`` attributes.
    """
    source_repo_name = _extract_repo_name(repo_url)
    target_repo_name = _extract_repo_name(target_work_area or repo_url)
    print(f"[gskill] Source corpus: {source_repo_name}")
    if target_repo_name != source_repo_name:
        print(f"[gskill] Target work area: {target_repo_name}")

    skill_suite: SkillSuite | None = None
    manifest_path = None
    if use_initial_skill:
        print("[gskill] Generating initial skill...")
        try:
            skill_suite = generate_initial_skill_suite(
                repo_url,
                model=skill_model,
                base_url=base_url,
                target_work_area_url=target_work_area,
            )
            if augment_suite:
                print("[gskill] Generating companion skills...")
                skill_suite = augment_skill_suite(
                    skill_suite,
                    repo_url=repo_url,
                    target_work_area_url=target_work_area,
                    model=skill_model,
                    base_url=base_url,
                )
            manifest_path = save_skill_suite(skill_suite, target_repo_name, output_dir)
            primary_chars = len(skill_suite.primary.content)
            print(
                f"[gskill] Initial workflow skill ({primary_chars} chars) saved to: "
                f"{manifest_path.parent / 'SKILL.md'}"
            )
            if skill_suite.companions:
                print(
                    f"[gskill] Companion skills: {len(skill_suite.companions)} saved via {manifest_path}"
                )
        except Exception as exc:
            print(f"[gskill] Warning: initial skill generation failed — {exc}")
            print("[gskill] Continuing without seed skill (GEPA will start from scratch).")
    else:
        print("[gskill] Skipping initial skill generation (--no-initial-skill).")

    if seed_only:
        if manifest_path:
            print(f"[gskill] Seed-only mode complete: {manifest_path}")
        else:
            print("[gskill] Seed-only mode complete with no generated skill.")
        return {
            "status": "seed_only",
            "repo_name": target_repo_name,
            "skill_path": str(manifest_path.parent / "SKILL.md") if manifest_path else None,
            "manifest_path": str(manifest_path) if manifest_path else None,
        }

    print("[gskill] Loading tasks from task sources...")
    selected_sources = task_sources or [DEFAULT_TASK_SOURCE]
    task_bundle_repo_url = target_work_area or repo_url
    task_bundle_limit = 300
    task_bundle_scratch_dir = Path("scratchpad") / "task-bundles" / target_repo_name.replace("/", "__")
    print(f"[gskill] Task sources: {', '.join(selected_sources)}")
    try:
        task_bundle, _task_bundle_request, selected_sources = _build_task_bundle(
            repo_name=target_repo_name,
            repo_url=task_bundle_repo_url,
            source_names=task_sources,
            limit=task_bundle_limit,
            scratch_dir=task_bundle_scratch_dir,
        )
    except ValueError as exc:
        if allow_missing_tasks:
            if manifest_path:
                print(f"[gskill] No SWE-smith tasks found for {target_repo_name}.")
                print(f"[gskill] Saved seed skill suite and exiting: {manifest_path}")
                return {
                    "status": "seed_saved_no_tasks",
                    "repo_name": target_repo_name,
                    "skill_path": str(manifest_path.parent / "SKILL.md"),
                    "manifest_path": str(manifest_path),
                    "reason": str(exc),
                }
            print(f"[gskill] No SWE-smith tasks found for {target_repo_name}.")
            print("[gskill] No seed skill is available to save, exiting without optimization.")
            return {
                "status": "no_tasks_no_seed",
                "repo_name": target_repo_name,
                "skill_path": None,
                "reason": str(exc),
            }
        raise
    train, val, test = task_bundle.train, task_bundle.val, task_bundle.test
    print(f"[gskill] Tasks: {len(train)} train / {len(val)} val / {len(test)} test")
    print(
        "[gskill] Task bundle context: "
        f"repo={target_repo_name} source={task_bundle_repo_url} "
        f"scratch={task_bundle_scratch_dir}"
    )

    evaluator = make_evaluator(agent_model=agent_model)
    seed_candidate = skill_suite.primary.content if skill_suite else None

    print(f"[gskill] Starting GEPA optimization (max_evals={max_evals})...")
    objective = (
        "Maximize the resolve rate on software engineering tasks "
        f"for the {target_repo_name} repository. "
        "The primary workflow skill should help the coding agent understand the target repo's "
        "validation commands, code structure, and change workflow."
    )
    if source_repo_name != target_repo_name:
        objective += (
            f" When useful, borrow distinctive engineering patterns from the source corpus "
            f"{source_repo_name}, but keep the skill grounded in {target_repo_name}'s actual work."
        )
    result = optimize_anything(
        seed_candidate=seed_candidate,
        evaluator=evaluator,
        dataset=train,
        valset=val,
        objective=objective,
        config=GEPAConfig(
            engine=EngineConfig(
                max_metric_calls=max_evals,
                raise_on_exception=False,
            ),
        ),
    )

    best_score = result.val_aggregate_scores[result.best_idx]
    if skill_suite:
        optimized_suite = SkillSuite(
            source_repo=skill_suite.source_repo,
            target_repo=skill_suite.target_repo,
            primary=skill_suite.primary,
            companions=skill_suite.companions,
        )
    else:
        optimized_suite = SkillSuite(
            source_repo=source_repo_name,
            target_repo=target_repo_name,
            primary=SkillArtifact(
                name=f"{target_repo_name.split('/')[-1]}-workflow",
                description=(
                    f"Workflow guidance for working in {target_repo_name} and validating changes "
                    "against its real task loop."
                ),
                content=result.best_candidate,
                role="primary",
            ),
            companions=[],
        )
    optimized_suite.primary = _artifact_from_content(
        content=result.best_candidate,
        fallback_name=optimized_suite.primary.name,
        fallback_description=optimized_suite.primary.description,
        role="primary",
    )
    if augment_suite:
        optimized_suite = augment_skill_suite(
            optimized_suite,
            repo_url=repo_url,
            target_work_area_url=target_work_area,
            model=skill_model,
            base_url=base_url,
        )
    manifest_path = save_skill_suite(optimized_suite, target_repo_name, output_dir)
    holdout_summary = None
    if run_test_eval and test:
        print("[gskill] Evaluating best skill on holdout test split...")
        holdout_summary = evaluate_holdout(
            evaluator=evaluator,
            candidate_skill=optimized_suite.primary.content,
            tasks=test,
            limit=test_eval_limit,
        )
        if holdout_summary["score"] is not None:
            print(
                f"[gskill] Holdout resolve rate: {holdout_summary['score']:.1%} "
                f"({holdout_summary['passed']}/{holdout_summary['attempted']})"
            )
        else:
            print("[gskill] Holdout evaluation skipped because no test tasks were selected.")
    report = {
        "source_repo": source_repo_name,
        "target_repo": target_repo_name,
        "max_evals": max_evals,
        "train_tasks": len(train),
        "val_tasks": len(val),
        "test_tasks": len(test),
        "task_bundle": {
            **task_bundle.provenance,
            "rejections": task_bundle.rejections,
            "request": {
                "repo_name": target_repo_name,
                "repo_url": task_bundle_repo_url,
                "limit": task_bundle_limit,
                "scratch_dir": str(task_bundle_scratch_dir),
            },
        },
        "task_sources": selected_sources,
        "best_val_score": best_score,
        "seed_used": seed_candidate is not None,
        "augment_suite": augment_suite,
        "manifest_path": str(manifest_path),
        "primary_skill": optimized_suite.primary.name,
        "companion_skills": [artifact.name for artifact in optimized_suite.companions],
        "holdout": holdout_summary,
    }
    report_path = save_run_report(report, target_repo_name, output_dir)
    print(f"[gskill] Best resolve rate: {best_score:.1%}")
    print(f"[gskill] Skill suite saved to: {manifest_path}")
    print(f"[gskill] Run report saved to: {report_path}")
    return result
