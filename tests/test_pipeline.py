"""Tests for pipeline orchestration."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from src import pipeline
from src.skill import SkillArtifact, SkillSuite
from src.tasks import EnvironmentSpec, TaskBundle, TaskSpec, VerifierSpec


def test_run_uses_target_work_area_for_tasks_and_saved_suite(monkeypatch, tmp_path):
    seed_suite = SkillSuite(
        source_repo="twilwa/api-design-skills-package-v2",
        target_repo="acme/commerce-api",
        primary=SkillArtifact(
            name="commerce-api-workflow",
            description="Workflow guidance for the commerce API repo.",
            content="---\nname: commerce-api-workflow\ndescription: Workflow guidance for the commerce API repo.\n---\n\nSeed body",
            role="primary",
        ),
        companions=[],
    )
    recorded: dict[str, object] = {}

    def fake_generate_initial_skill_suite(repo_url, target_work_area_url=None, model=None, base_url=None):
        recorded["generated_for"] = (repo_url, target_work_area_url)
        return seed_suite

    bundle = TaskBundle(
        tasks=[
            TaskSpec(
                id="1",
                family="benchmark",
                source="swe-smith",
                repo_name="acme/commerce-api",
                problem_statement="Fix issue 1",
                environment=EnvironmentSpec(kind="swebench_docker", ref="repo@1"),
                verifier=VerifierSpec(kind="test_selectors", selectors=["tests/test_one.py::test_case"]),
                metadata={"instance_id": "1"},
            ),
            TaskSpec(
                id="2",
                family="benchmark",
                source="swe-smith",
                repo_name="acme/commerce-api",
                problem_statement="Fix issue 2",
                environment=EnvironmentSpec(kind="swebench_docker", ref="repo@2"),
                verifier=VerifierSpec(kind="test_selectors", selectors=["tests/test_two.py::test_case"]),
                metadata={"instance_id": "2"},
            ),
            TaskSpec(
                id="3",
                family="benchmark",
                source="swe-smith",
                repo_name="acme/commerce-api",
                problem_statement="Fix issue 3",
                environment=EnvironmentSpec(kind="swebench_docker", ref="repo@3"),
                verifier=VerifierSpec(kind="test_selectors", selectors=["tests/test_three.py::test_case"]),
                metadata={"instance_id": "3"},
            ),
        ],
        train=[],
        val=[],
        test=[],
        provenance={"source_counts": {"swe-smith": 3}, "sources": ["swe-smith"]},
    )
    bundle = TaskBundle(
        tasks=bundle.tasks,
        train=bundle.tasks[:1],
        val=bundle.tasks[1:2],
        test=bundle.tasks[2:],
        provenance=bundle.provenance,
    )

    def fake_build_task_bundle(repo_name, source_names=None, limit=300, train=0.67, val=0.17):
        recorded["task_repo"] = repo_name
        recorded["task_sources"] = source_names
        return bundle

    def fake_make_evaluator(agent_model=None):
        recorded["agent_model"] = agent_model
        return "evaluator"

    def fake_optimize_anything(*, seed_candidate, evaluator, dataset, valset, objective, config):
        recorded["objective"] = objective
        return SimpleNamespace(
            best_candidate="---\nname: commerce-api-workflow\ndescription: Optimized workflow guidance.\n---\n\nOptimized body",
            val_aggregate_scores=[0.75],
            best_idx=0,
        )

    def fake_augment_skill_suite(skill_suite, repo_url, target_work_area_url=None, model=None, base_url=None):
        recorded["augmented_for"] = (repo_url, target_work_area_url)
        return SkillSuite(
            source_repo=skill_suite.source_repo,
            target_repo=skill_suite.target_repo,
            primary=skill_suite.primary,
            companions=[
                SkillArtifact(
                    name="api-design-reviewer",
                    description="Reusable API review guidance.",
                    content="---\nname: api-design-reviewer\ndescription: Reusable API review guidance.\n---\n\nReview body",
                    role="companion",
                )
            ],
        )

    def fake_save_skill_suite(skill_suite, repo_name, output_dir):
        recorded["saved_repo"] = repo_name
        recorded["saved_suite"] = skill_suite
        return tmp_path / "skill-suite.json"

    def fake_evaluate_holdout(evaluator, candidate_skill, tasks, limit=None):
        recorded["holdout"] = {
            "candidate": candidate_skill,
            "tasks": tasks,
            "limit": limit,
        }
        return {
            "attempted": 1,
            "passed": 1,
            "score": 1.0,
            "instances": ["3"],
        }

    def fake_save_run_report(report, repo_name, output_dir):
        recorded["report_repo"] = repo_name
        recorded["report"] = report
        return Path(tmp_path) / "run-report.json"

    monkeypatch.setattr(pipeline, "generate_initial_skill_suite", fake_generate_initial_skill_suite)
    monkeypatch.setattr(pipeline, "build_task_bundle", fake_build_task_bundle)
    monkeypatch.setattr(pipeline, "make_evaluator", fake_make_evaluator)
    monkeypatch.setattr(pipeline, "optimize_anything", fake_optimize_anything)
    monkeypatch.setattr(pipeline, "augment_skill_suite", fake_augment_skill_suite)
    monkeypatch.setattr(pipeline, "save_skill_suite", fake_save_skill_suite)
    monkeypatch.setattr(pipeline, "evaluate_holdout", fake_evaluate_holdout)
    monkeypatch.setattr(pipeline, "save_run_report", fake_save_run_report)

    pipeline.run(
        repo_url="https://github.com/twilwa/api-design-skills-package-v2",
        target_work_area="https://github.com/acme/commerce-api",
        output_dir=str(tmp_path),
        max_evals=5,
        task_sources=["swe-smith"],
        run_test_eval=True,
        test_eval_limit=1,
    )

    assert recorded["generated_for"] == (
        "https://github.com/twilwa/api-design-skills-package-v2",
        "https://github.com/acme/commerce-api",
    )
    assert recorded["task_repo"] == "acme/commerce-api"
    assert "acme/commerce-api" in recorded["objective"]
    assert "twilwa/api-design-skills-package-v2" in recorded["objective"]
    assert recorded["saved_repo"] == "acme/commerce-api"
    saved_suite = recorded["saved_suite"]
    assert isinstance(saved_suite, SkillSuite)
    assert saved_suite.primary.content.strip().endswith("Optimized body")
    assert saved_suite.companions[0].name == "api-design-reviewer"
    assert recorded["task_sources"] == ["swe-smith"]
    assert recorded["holdout"]["limit"] == 1
    assert recorded["report_repo"] == "acme/commerce-api"
    assert recorded["report"]["holdout"]["score"] == 1.0
    assert recorded["report"]["task_bundle"]["source_counts"] == {"swe-smith": 3}


def test_run_passes_repo_url_and_preserves_python_mutation_provenance(monkeypatch, tmp_path):
    seed_suite = SkillSuite(
        source_repo="twilwa/api-design-skills-package-v2",
        target_repo="acme/commerce-api",
        primary=SkillArtifact(
            name="commerce-api-workflow",
            description="Workflow guidance for the commerce API repo.",
            content="---\nname: commerce-api-workflow\ndescription: Workflow guidance for the commerce API repo.\n---\n\nSeed body",
            role="primary",
        ),
        companions=[],
    )
    recorded: dict[str, object] = {}

    def fake_generate_initial_skill_suite(repo_url, target_work_area_url=None, model=None, base_url=None):
        return seed_suite

    bundle = TaskBundle(
        tasks=[
            TaskSpec(
                id="mutation-1",
                family="mutation",
                source="python-mutation",
                repo_name="acme/commerce-api",
                problem_statement="Flip the add implementation.",
                environment=EnvironmentSpec(kind="local_checkout", ref="/tmp/mutation-1"),
                verifier=VerifierSpec(kind="shell_command", commands=("uv run pytest",)),
                metadata={
                    "mutation_source": {
                        "kind": "python",
                        "validation_command": "uv run pytest",
                    }
                },
            )
        ],
        train=[],
        val=[],
        test=[],
        provenance={
            "source_counts": {"python-mutation": 1},
            "sources": ["python-mutation"],
            "mutation_source": {
                "kind": "python",
                "repo_url": "https://github.com/acme/commerce-api",
            },
        },
    )
    bundle = TaskBundle(
        tasks=bundle.tasks,
        train=bundle.tasks,
        val=[],
        test=[],
        provenance=bundle.provenance,
    )

    def fake_build_task_bundle(
        repo_name,
        source_names=None,
        limit=300,
        train=0.67,
        val=0.17,
        repo_url=None,
        scratch_dir=None,
    ):
        recorded["task_repo"] = repo_name
        recorded["task_sources"] = source_names
        return bundle

    def fake_make_evaluator(agent_model=None):
        return "evaluator"

    def fake_optimize_anything(*, seed_candidate, evaluator, dataset, valset, objective, config):
        return SimpleNamespace(
            best_candidate="---\nname: commerce-api-workflow\ndescription: Optimized workflow guidance.\n---\n\nOptimized body",
            val_aggregate_scores=[0.75],
            best_idx=0,
        )

    def fake_save_skill_suite(skill_suite, repo_name, output_dir):
        return tmp_path / "skill-suite.json"

    def fake_save_run_report(report, repo_name, output_dir):
        recorded["report"] = report
        return Path(tmp_path) / "run-report.json"

    monkeypatch.setattr(pipeline, "generate_initial_skill_suite", fake_generate_initial_skill_suite)
    monkeypatch.setattr(pipeline, "build_task_bundle", fake_build_task_bundle)
    monkeypatch.setattr(pipeline, "make_evaluator", fake_make_evaluator)
    monkeypatch.setattr(pipeline, "optimize_anything", fake_optimize_anything)
    monkeypatch.setattr(pipeline, "save_skill_suite", fake_save_skill_suite)
    monkeypatch.setattr(pipeline, "save_run_report", fake_save_run_report)

    pipeline.run(
        repo_url="https://github.com/twilwa/api-design-skills-package-v2",
        target_work_area="https://github.com/acme/commerce-api",
        output_dir=str(tmp_path),
        max_evals=5,
        task_sources=["python-mutation"],
        augment_suite=False,
        run_test_eval=False,
    )

    assert recorded["task_repo"] == "acme/commerce-api"
    assert recorded["task_sources"] == ["python-mutation"]
    assert recorded["report"]["task_bundle"]["request"] == {
        "repo_name": "acme/commerce-api",
        "repo_url": "https://github.com/acme/commerce-api",
        "limit": 300,
        "scratch_dir": "scratchpad/task-bundles/acme__commerce-api",
    }
    assert recorded["report"]["task_bundle"]["source_counts"] == {"python-mutation": 1}
    assert recorded["report"]["task_bundle"]["sources"] == ["python-mutation"]
    assert recorded["report"]["task_bundle"]["mutation_source"] == {
        "kind": "python",
        "repo_url": "https://github.com/acme/commerce-api",
    }
