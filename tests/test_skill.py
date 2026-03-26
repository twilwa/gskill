"""Tests for skill suite generation and persistence."""

from __future__ import annotations

import json

from src.skill import (
    SkillArtifact,
    SkillSuite,
    _build_fallback_companion_skills,
    save_skill_suite,
)


def test_save_skill_suite_writes_primary_manifest_and_companions(tmp_path):
    suite = SkillSuite(
        source_repo="twilwa/api-design-skills-package-v2",
        target_repo="twilwa/api-design-skills-package-v2",
        primary=SkillArtifact(
            name="api-design-skills-package-v2-workflow",
            description="Workflow guidance for the target repository.",
            content="---\nname: api-design-skills-package-v2-workflow\ndescription: Workflow guidance for the target repository.\n---\n\nBody",
            role="primary",
        ),
        companions=[
            SkillArtifact(
                name="api-design-reviewer",
                description="Reusable API review guidance.",
                content="---\nname: api-design-reviewer\ndescription: Reusable API review guidance.\n---\n\nReview body",
                role="companion",
            )
        ],
    )

    manifest_path = save_skill_suite(suite, "twilwa/api-design-skills-package-v2", str(tmp_path))
    manifest = json.loads(manifest_path.read_text())

    repo_dir = tmp_path / "api-design-skills-package-v2"
    assert (repo_dir / "SKILL.md").read_text() == suite.primary.content
    assert (repo_dir / "api-design-reviewer" / "SKILL.md").read_text() == suite.companions[0].content
    assert manifest["source_repo"] == "twilwa/api-design-skills-package-v2"
    assert manifest["target_repo"] == "twilwa/api-design-skills-package-v2"
    assert manifest["primary"]["name"] == "api-design-skills-package-v2-workflow"
    assert manifest["companions"][0]["path"] == "api-design-reviewer/SKILL.md"


def test_build_fallback_companion_skills_for_api_corpus():
    repo_text = """
    This TypeScript corpus compares REST, GraphQL, gRPC, async jobs, webhooks,
    version governance, OpenAPI, and API gateway / BFF patterns.
    """

    companions = _build_fallback_companion_skills(
        source_repo_name="twilwa/api-design-skills-package-v2",
        target_repo_name="twilwa/api-design-skills-package-v2",
        repo_text=repo_text,
    )

    names = [artifact.name for artifact in companions]
    assert "api-design-reviewer" in names
    assert "api-lifecycle-manager" in names
    assert "api-architecture-patterns" in names
