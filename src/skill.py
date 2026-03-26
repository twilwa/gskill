"""Initial skill generation, augmentation, and skill suite file I/O."""

from __future__ import annotations

import base64
import json
import os
import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import openai

CONTEXT_CANDIDATES = [
    "AGENTS.md",
    "CLAUDE.md",
    "CONTRIBUTING.md",
    "DEVELOPMENT.md",
    "SEED-SKILL.md",
    "USE-WITH-GSKILL.md",
    "repo-manifest.json",
    "training/skill-slices.json",
    "docs/architecture.md",
    "docs/development.md",
    "docs/testing.md",
    "pyproject.toml",
    "setup.cfg",
    "tox.ini",
    "pytest.ini",
    "package.json",
    "pnpm-workspace.yaml",
    "tsconfig.json",
    "Cargo.toml",
    "go.mod",
    "Gemfile",
    "Taskfile.yml",
    "Makefile",
]


@dataclass(slots=True)
class SkillArtifact:
    """A single saved skill."""

    name: str
    description: str
    content: str
    role: str = "companion"


@dataclass(slots=True)
class SkillSuite:
    """A package of repo workflow guidance plus companion skills."""

    source_repo: str
    target_repo: str
    primary: SkillArtifact
    companions: list[SkillArtifact]


def _make_skill_name(repo: str) -> str:
    """Sanitize a repo short name into a valid skill name."""
    name = repo.lower()
    name = re.sub(r"[^a-z0-9]+", "-", name)
    name = name.strip("-")
    return name[:64]


def _parse_repo_name(repo_or_url: str) -> tuple[str, str]:
    """Parse ``owner/repo`` from a GitHub URL or an ``owner/repo`` string."""
    text = repo_or_url.rstrip("/")
    if "github.com/" in text:
        text = text.split("github.com/")[-1]
    parts = [part for part in text.split("/") if part]
    if len(parts) < 2:
        raise ValueError(
            f"Expected a GitHub URL or 'owner/repo' string, got {repo_or_url!r}"
        )
    return parts[0], parts[1]


def _normalize_repo_name(repo_or_url: str) -> str:
    """Return a normalized ``owner/repo`` name."""
    owner, repo = _parse_repo_name(repo_or_url)
    return f"{owner}/{repo}"


def _make_workflow_skill_name(repo_name: str) -> str:
    """Build the primary workflow skill name for a work area."""
    short_name = repo_name.split("/")[-1]
    return _make_skill_name(f"{short_name}-workflow")


def _fetch_readme(owner: str, repo: str, max_chars: int = 3000) -> str:
    """Fetch the README from GitHub API."""
    url = f"https://api.github.com/repos/{owner}/{repo}/readme"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "gskill/0.1"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            content = base64.b64decode(data["content"]).decode(
                "utf-8", errors="replace"
            )
            return content[:max_chars]
    except Exception:
        return ""


def _fetch_file(owner: str, repo: str, path: str, max_chars: int = 2000) -> str:
    """Fetch a specific file from GitHub API."""
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "gskill/0.1"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            if data.get("encoding") == "base64":
                content = base64.b64decode(data["content"]).decode(
                    "utf-8", errors="replace"
                )
                return content[:max_chars]
    except Exception:
        pass
    return ""


def _fetch_repo_context(owner: str, repo: str, max_chars: int = 12000) -> str:
    """Fetch a bundle of high-signal repo files for synthesis."""
    blocks: list[str] = []
    remaining = max_chars
    for candidate in CONTEXT_CANDIDATES:
        if remaining <= 0:
            break
        content = _fetch_file(owner, repo, candidate, max_chars=min(remaining, 2000))
        if not content:
            continue
        blocks.append(f"### {candidate}\n```\n{content}\n```")
        remaining -= len(content)
    return "\n\n".join(blocks)


def _context_files(extra_context: str) -> list[str]:
    """Extract fetched file names from the rendered context block."""
    return re.findall(r"^### ([^\n]+)$", extra_context, flags=re.MULTILINE)


def _infer_test_commands(*texts: str) -> list[str]:
    """Infer likely validation commands from fetched repo context."""
    lower = "\n".join(texts).lower()
    commands: list[str] = []
    candidates = [
        "make verify",
        "make test",
        "task test",
        "npm run verify",
        "npm run typecheck",
        "npm test",
        "pnpm test",
        "bun test",
        "uv run pytest",
        "pytest",
        "tox",
        "cargo test",
        "go test ./...",
    ]
    for candidate in candidates:
        if candidate in lower and candidate not in commands:
            commands.append(candidate)
    if not commands:
        commands.append(
            "inspect the repo config and run the project validation command before editing"
        )
    return commands


def _sanitize_description(description: str, fallback: str) -> str:
    """Normalize descriptions for frontmatter."""
    cleaned = re.sub(r"<[^>]+>", "", description or "").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned[:1024] or fallback


def _format_skill_content(name: str, description: str, body: str) -> str:
    """Render a complete SKILL.md document."""
    return (
        f"---\nname: {name}\ndescription: {description}\n---\n\n{body.strip()}\n"
    )


def _artifact_from_content(
    content: str, fallback_name: str, fallback_description: str, role: str
) -> SkillArtifact:
    """Parse frontmatter from a skill file if present."""
    frontmatter_match = re.match(r"^---\n(.*?)\n---\n?(.*)$", content, re.DOTALL)
    name = fallback_name
    description = fallback_description
    if frontmatter_match:
        frontmatter = frontmatter_match.group(1)
        body = frontmatter_match.group(2).strip()
        name_match = re.search(r"^name:\s*(.+)$", frontmatter, flags=re.MULTILINE)
        description_match = re.search(
            r"^description:\s*(.+)$", frontmatter, flags=re.MULTILINE
        )
        if name_match:
            name = _make_skill_name(name_match.group(1).strip())
        if description_match:
            description = _sanitize_description(
                description_match.group(1).strip(), fallback_description
            )
        content = _format_skill_content(name, description, body)
    return SkillArtifact(
        name=name,
        description=description,
        content=content,
        role=role,
    )


def _resolve_openai_settings(
    model: str | None,
    base_url: str | None,
    *,
    model_env_var: str = "GSKILL_SKILL_MODEL",
    default_model: str = "gpt-5.2",
) -> tuple[str, dict[str, Any], bool]:
    """Resolve model settings and whether model-backed generation is available."""
    resolved_base_url = base_url or os.environ.get("OPENAI_BASE_URL")
    resolved_model = model or os.environ.get(model_env_var)

    if resolved_base_url and not resolved_model:
        raise ValueError(
            "A custom base URL is set but no skill model was specified. "
            "Use --skill-model or set GSKILL_SKILL_MODEL to the model name your local backend serves."
        )

    resolved_model = resolved_model or default_model
    if "/" in resolved_model:
        resolved_model = resolved_model.split("/", 1)[1]

    client_kwargs: dict[str, Any] = {}
    if resolved_base_url:
        client_kwargs["base_url"] = resolved_base_url
    if not os.environ.get("OPENAI_API_KEY") and resolved_base_url:
        client_kwargs["api_key"] = "none"

    has_model_access = bool(os.environ.get("OPENAI_API_KEY") or resolved_base_url)
    return resolved_model, client_kwargs, has_model_access


def _extract_json_object(text: str) -> dict[str, Any]:
    """Extract and decode the first JSON object from a model response."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Model response did not contain a JSON object.")
    return json.loads(text[start : end + 1])


def _build_fallback_primary_skill(
    *,
    source_repo_url: str,
    source_repo_name: str,
    target_repo_name: str,
    target_readme: str,
    target_context: str,
    source_context: str,
) -> SkillArtifact:
    """Build a deterministic workflow skill when LLM generation is unavailable."""
    workflow_name = _make_workflow_skill_name(target_repo_name)
    test_commands = _infer_test_commands(target_readme, target_context)
    tests_text = ", ".join(f"`{command}`" for command in test_commands)
    context_files = _context_files(target_context)
    structure_text = (
        ", ".join(context_files[:6])
        if context_files
        else "the README and primary build/test configuration files"
    )
    target_short = target_repo_name.split("/")[-1]
    source_clause = ""
    if source_repo_name != target_repo_name:
        source_clause = (
            f"\n\nUse `{source_repo_name}` as a domain/pattern corpus when it helps with "
            f"the work in `{target_repo_name}`, but keep workflow instructions grounded in the target repo."
        )

    body = f"""Use this skill when working in `{target_repo_name}`. It captures how to navigate the repo, validate changes, and borrow relevant patterns without drifting into generic advice.{source_clause}

## 1. Test commands

Start by confirming the repo's documented validation path, then run the narrowest relevant command before and after changes: {tests_text}.

## 2. Code structure

Orient from the repository root first. The highest-signal artifacts visible from static analysis are {structure_text}. Read the README and the build/test configuration before changing code, because this repo likely exposes its actual workflow there more clearly than a framework-default layout would.

## 3. Conventions

Match the repository's existing language, naming, and file-placement conventions. Preserve the command paths, scripts, and contract files already used by the repo. If the work depends on a source corpus of patterns, use that corpus to improve design decisions without overwriting the target repo's own workflow.

## 4. Common pitfalls

Do not invent commands, package managers, or service boundaries. Do not assume a Python workflow unless the repo says so. Verify whether validation means tests, typechecking, generation, contract checks, or a combination before editing. If code and generated outputs diverge, treat the documented source inputs as authoritative unless the repo states otherwise.

## 5. Workflow

Read the README first. Identify the smallest set of files that own the behavior you need to change. Reproduce with the repo's real command path, patch the narrowest possible surface, and rerun the same validation. If the task is design-heavy, cross-check the relevant pattern corpus before finalizing the change.

Repository URL: {source_repo_url}

README excerpt for `{target_short}`:

{target_readme[:1200].strip() or "README was not available."}
"""

    description = (
        f"Use this skill when working in the {target_short} repository to navigate its workflow, "
        "run the right validation commands, and stay aligned with its actual development patterns."
    )
    return SkillArtifact(
        name=workflow_name,
        description=_sanitize_description(description, description),
        content=_format_skill_content(workflow_name, description, body),
        role="primary",
    )


def _build_transfer_skill(
    *,
    name: str,
    description: str,
    source_repo_name: str,
    target_repo_name: str,
    when_to_use: str,
    corpus_signals: list[str],
    workflow: list[str],
    pitfalls: list[str],
) -> SkillArtifact:
    """Build a deterministic reusable companion skill."""
    signal_text = "\n".join(f"- {signal}" for signal in corpus_signals)
    workflow_text = "\n".join(f"{idx}. {step}" for idx, step in enumerate(workflow, start=1))
    pitfalls_text = "\n".join(f"- {pitfall}" for pitfall in pitfalls)
    body = f"""Load this skill when continuing development in `{target_repo_name}` and the task matches the capability below. It was extracted from `{source_repo_name}` as a reusable development aid rather than repo-workflow instructions.

## When to use

{when_to_use}

## Relevant corpus signals

{signal_text}

## Workflow

{workflow_text}

## Pitfalls

{pitfalls_text}
"""
    skill_name = _make_skill_name(name)
    cleaned_description = _sanitize_description(description, description)
    return SkillArtifact(
        name=skill_name,
        description=cleaned_description,
        content=_format_skill_content(skill_name, cleaned_description, body),
        role="companion",
    )


def _build_fallback_companion_skills(
    source_repo_name: str,
    target_repo_name: str,
    repo_text: str,
) -> list[SkillArtifact]:
    """Infer reusable companion skills from repo text without an LLM."""
    lower = repo_text.lower()
    if any(
        keyword in lower
        for keyword in [
            "openapi",
            "graphql",
            "grpc",
            "webhook",
            "rest",
            "api gateway",
            "bff",
            "version governance",
            "problem details",
        ]
    ):
        return [
            _build_transfer_skill(
                name="api-design-reviewer",
                description="Review and improve API contracts, semantics, and interface clarity using the source corpus.",
                source_repo_name=source_repo_name,
                target_repo_name=target_repo_name,
                when_to_use=(
                    "Use this for tasks that reshape external interfaces, error semantics, "
                    "pagination, idempotency, contract readability, or consumer-facing API consistency."
                ),
                corpus_signals=[
                    "Contrastive examples across REST, GraphQL, and gRPC.",
                    "Explicit contract artifacts such as OpenAPI, GraphQL SDL, and protobuf.",
                    "Review rubrics and pattern-selection notes in the corpus docs.",
                ],
                workflow=[
                    "Start from the contract surface before the handler implementation.",
                    "Check whether the interface is clear to both humans and coding agents.",
                    "Verify pagination, idempotency, and error semantics instead of only payload shape.",
                ],
                pitfalls=[
                    "Leaking internal storage or service boundaries into the public interface.",
                    "Changing transport shape without updating the corresponding contract file.",
                ],
            ),
            _build_transfer_skill(
                name="api-lifecycle-manager",
                description="Design versioning, deprecation, migration, and lifecycle signals using the corpus as a guide.",
                source_repo_name=source_repo_name,
                target_repo_name=target_repo_name,
                when_to_use=(
                    "Use this when a task touches version negotiation, deprecation headers, compatibility windows, "
                    "migration paths, or stable aliases."
                ),
                corpus_signals=[
                    "Version-handle patterns and version catalogs in the source corpus.",
                    "Migration notes and machine-readable lifecycle metadata.",
                    "Examples that separate external stability from backend evolution.",
                ],
                workflow=[
                    "Identify which consumers need pinned behavior versus movable aliases.",
                    "Keep migration metadata explicit and machine-readable.",
                    "Prefer stable external handles over scattering version details through the codebase.",
                ],
                pitfalls=[
                    "Treating versioning as only a URL path rename.",
                    "Using a `stable` alias when consumers need deterministic compatibility.",
                ],
            ),
            _build_transfer_skill(
                name="api-architecture-patterns",
                description="Choose among gateway, BFF, composition, and transport patterns with clear tradeoffs.",
                source_repo_name=source_repo_name,
                target_repo_name=target_repo_name,
                when_to_use=(
                    "Use this for tasks that introduce or refactor service boundaries, edge orchestration, "
                    "transport choices, or cross-service aggregation."
                ),
                corpus_signals=[
                    "Separate examples for API gateway/facade, backend-for-frontend, and API composition.",
                    "Transport comparisons across REST, GraphQL, and gRPC.",
                    "Async-job and webhook patterns for non-synchronous integrations.",
                ],
                workflow=[
                    "Map the actual consumers and ownership boundaries first.",
                    "Choose the smallest pattern that hides instability without creating a pass-through façade.",
                    "Check whether the change belongs at the edge, in composition, or in the service itself.",
                ],
                pitfalls=[
                    "Confusing BFFs with generic gateway logic.",
                    "Adding orchestration layers without clarifying what instability they absorb.",
                ],
            ),
        ]

    generic_name = _make_skill_name(f"{target_repo_name.split('/')[-1]}-development-patterns")
    return [
        _build_transfer_skill(
            name=generic_name,
            description="Reusable development patterns extracted from the source corpus for ongoing coding work.",
            source_repo_name=source_repo_name,
            target_repo_name=target_repo_name,
            when_to_use=(
                "Use this when the target repo needs domain-specific coding guidance that goes beyond repo workflow instructions."
            ),
            corpus_signals=[
                "The source corpus highlights recurring design and implementation concerns.",
                "The repository README and config files point to distinctive task patterns.",
            ],
            workflow=[
                "Read the relevant corpus documents before changing implementation details.",
                "Apply the extracted patterns only where they match the target repo's actual boundaries.",
                "Re-validate in the target repo after each meaningful change.",
            ],
            pitfalls=[
                "Copying the source corpus literally instead of translating it into the target repo's context.",
            ],
        )
    ]


def generate_initial_skill_suite(
    repo_url: str,
    model: str | None = None,
    base_url: str | None = None,
    target_work_area_url: str | None = None,
) -> SkillSuite:
    """Generate the initial workflow skill for a repo or target work area."""
    source_repo_name = _normalize_repo_name(repo_url)
    source_owner, source_repo = _parse_repo_name(repo_url)
    target_repo_name = _normalize_repo_name(target_work_area_url or repo_url)
    target_owner, target_repo = _parse_repo_name(target_work_area_url or repo_url)

    source_readme = _fetch_readme(source_owner, source_repo)
    source_context = _fetch_repo_context(source_owner, source_repo)
    if target_repo_name == source_repo_name:
        target_readme = source_readme
        target_context = source_context
    else:
        target_readme = _fetch_readme(target_owner, target_repo)
        target_context = _fetch_repo_context(target_owner, target_repo)

    primary_name = _make_workflow_skill_name(target_repo_name)
    description_fallback = (
        f"Use this skill when working in {target_repo_name} to navigate the repo, run the right validation commands, "
        "and stay aligned with its real development workflow."
    )

    resolved_model, client_kwargs, has_model_access = _resolve_openai_settings(
        model=model, base_url=base_url
    )

    if not has_model_access:
        primary = _build_fallback_primary_skill(
            source_repo_url=repo_url,
            source_repo_name=source_repo_name,
            target_repo_name=target_repo_name,
            target_readme=target_readme,
            target_context=target_context,
            source_context=source_context,
        )
        return SkillSuite(
            source_repo=source_repo_name,
            target_repo=target_repo_name,
            primary=primary,
            companions=[],
        )

    client = openai.OpenAI(**client_kwargs)
    target_clause = ""
    if source_repo_name != target_repo_name:
        target_clause = f"""
Target work area repository: {target_repo_name}

Target work area README (may be truncated):
{target_readme}

Target work area context files:
{target_context}
"""

    try:
        message = client.chat.completions.create(
            model=resolved_model,
            max_completion_tokens=2200,
            messages=[
                {
                    "role": "user",
                    "content": f"""You are generating the primary workflow skill for a coding agent.

The agent will continue working in the target repository and should use this skill to understand how to make changes there. If a source corpus repository is provided, use it only to improve task-relevant engineering judgment without replacing the target repo's actual workflow.

Source corpus repository: {source_repo_name}
Source corpus URL: {repo_url}

Source corpus README (may be truncated):
{source_readme}

Source corpus context files:
{source_context}
{target_clause}

Output a complete SKILL.md starting with YAML frontmatter, then the body. Use exactly this structure:

---
name: {primary_name}
description: <one-sentence description, max 1024 characters, no angle-bracket XML tags>
---

<body: 400-900 words covering the five sections below>

The body must cover:

1. **Test commands**: The exact validation commands to run in the target work area. Include the narrowest useful variants when relevant.
2. **Code structure**: Key directories, contracts, or build files in the target work area that control real engineering changes.
3. **Conventions**: The repo's actual implementation and workflow patterns. If there is a source corpus, explain how to consult it without overriding the target repo.
4. **Common pitfalls**: Mistakes an agent is likely to make in this target repo.
5. **Workflow**: A practical diagnose → patch → verify loop for the target repo.

Constraints:
- The `name` field must be exactly: {primary_name}
- The description must be non-empty, at most 1024 characters, and must not contain angle-bracket XML tags.
- Keep the skill grounded in the target work area's actual commands and structure.
- Avoid generic language that could apply to any Python or TypeScript project.
- If source corpus and target work area differ, make that distinction explicit in the body.""",
                }
            ],
        )
    except openai.APIStatusError as exc:
        endpoint = client_kwargs.get("base_url") or "https://api.openai.com"
        raise RuntimeError(
            f"Skill generation failed — HTTP {exc.status_code} from {endpoint!r} "
            f"with model {resolved_model!r}: {exc.message}"
        ) from exc
    except openai.APIConnectionError as exc:
        endpoint = client_kwargs.get("base_url") or "https://api.openai.com"
        raise RuntimeError(
            f"Skill generation failed — could not connect to {endpoint!r}: {exc}"
        ) from exc

    content = message.choices[0].message.content
    if not content:
        raise RuntimeError(
            f"Skill generation failed — model {resolved_model!r} returned an empty response "
            "(the model may have invoked a tool instead of generating text, or the response was filtered)"
        )

    primary = _artifact_from_content(
        content=content,
        fallback_name=primary_name,
        fallback_description=description_fallback,
        role="primary",
    )
    return SkillSuite(
        source_repo=source_repo_name,
        target_repo=target_repo_name,
        primary=primary,
        companions=[],
    )


def generate_initial_skill(
    repo_url: str,
    model: str | None = None,
    base_url: str | None = None,
    target_work_area_url: str | None = None,
) -> str:
    """Generate the primary seed skill content for backward compatibility."""
    return generate_initial_skill_suite(
        repo_url=repo_url,
        model=model,
        base_url=base_url,
        target_work_area_url=target_work_area_url,
    ).primary.content


def augment_skill_suite(
    skill_suite: SkillSuite,
    repo_url: str,
    target_work_area_url: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
) -> SkillSuite:
    """Generate companion skills that complement the primary workflow skill."""
    source_repo_name = _normalize_repo_name(repo_url)
    source_owner, source_repo = _parse_repo_name(repo_url)
    target_repo_name = _normalize_repo_name(target_work_area_url or repo_url)
    target_owner, target_repo = _parse_repo_name(target_work_area_url or repo_url)

    source_readme = _fetch_readme(source_owner, source_repo)
    source_context = _fetch_repo_context(source_owner, source_repo)
    if source_repo_name == target_repo_name:
        target_readme = source_readme
        target_context = source_context
    else:
        target_readme = _fetch_readme(target_owner, target_repo)
        target_context = _fetch_repo_context(target_owner, target_repo)

    repo_text = "\n".join(
        [
            source_readme,
            source_context,
            target_readme,
            target_context,
            skill_suite.primary.content,
        ]
    )
    fallback_companions = _build_fallback_companion_skills(
        source_repo_name=source_repo_name,
        target_repo_name=target_repo_name,
        repo_text=repo_text,
    )

    resolved_model, client_kwargs, has_model_access = _resolve_openai_settings(
        model=model, base_url=base_url
    )
    if not has_model_access:
        return SkillSuite(
            source_repo=skill_suite.source_repo,
            target_repo=skill_suite.target_repo,
            primary=skill_suite.primary,
            companions=fallback_companions,
        )

    client = openai.OpenAI(**client_kwargs)
    target_clause = ""
    if source_repo_name != target_repo_name:
        target_clause = f"""
Target work area repository: {target_repo_name}
Target work area README (may be truncated):
{target_readme}

Target work area context files:
{target_context}
"""

    suggested_names = ", ".join(artifact.name for artifact in fallback_companions)
    try:
        message = client.chat.completions.create(
            model=resolved_model,
            max_completion_tokens=2800,
            messages=[
                {
                    "role": "user",
                    "content": f"""You are generating a companion skill suite for a coding agent.

The primary workflow skill below tells the agent how to work in the target repository. Your job is to add 2 to 4 reusable companion skills that improve the agent's development capabilities for the kind of work represented by the source corpus.

Primary workflow skill:
{skill_suite.primary.content}

Source corpus repository: {source_repo_name}
Source corpus README (may be truncated):
{source_readme}

Source corpus context files:
{source_context}
{target_clause}

Heuristic companion suggestions: {suggested_names}

Return JSON only in this shape:
{{
  "companions": [
    {{
      "name": "kebab-case-skill-name",
      "description": "one sentence, max 1024 chars",
      "body_markdown": "Markdown body with sections '## When to use', '## Relevant corpus signals', '## Workflow', and '## Pitfalls'."
    }}
  ]
}}

Constraints:
- Each companion skill must be a reusable capability, not repo workflow instructions.
- Each companion must help with development tasks likely to show up while continuing work in the target repo.
- Ground each companion in the source corpus; do not invent capabilities unsupported by the repo context.
- Do not duplicate the primary workflow skill.
- Use unique names. Avoid the target repo name unless it adds real clarity.
- Prefer the smallest set of high-value skills over a broad weak list.""",
                }
            ],
        )
        content = message.choices[0].message.content or ""
        payload = _extract_json_object(content)
        companions_data = payload.get("companions", [])
    except Exception:
        companions_data = []

    companions: list[SkillArtifact] = []
    seen_names = {skill_suite.primary.name}
    for item in companions_data:
        raw_name = str(item.get("name", "")).strip()
        body = str(item.get("body_markdown", "")).strip()
        if not raw_name or not body:
            continue
        name = _make_skill_name(raw_name)
        if not name or name in seen_names:
            continue
        description = _sanitize_description(
            str(item.get("description", "")).strip(),
            f"Reusable development guidance extracted from {source_repo_name}.",
        )
        companions.append(
            SkillArtifact(
                name=name,
                description=description,
                content=_format_skill_content(name, description, body),
                role="companion",
            )
        )
        seen_names.add(name)
        if len(companions) == 4:
            break

    if not companions:
        companions = fallback_companions

    return SkillSuite(
        source_repo=skill_suite.source_repo,
        target_repo=skill_suite.target_repo,
        primary=skill_suite.primary,
        companions=companions,
    )


def save_skill(skill: str, repo_name: str, output_dir: str = ".claude/skills") -> Path:
    """Write the primary skill to ``{output_dir}/{short_repo_name}/SKILL.md``."""
    short_name = repo_name.split("/")[-1]
    path = Path(output_dir) / short_name / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(skill)
    return path


def save_skill_suite(
    skill_suite: SkillSuite,
    repo_name: str,
    output_dir: str = ".claude/skills",
) -> Path:
    """Persist a skill suite and return the manifest path."""
    short_name = repo_name.split("/")[-1]
    root = Path(output_dir) / short_name
    root.mkdir(parents=True, exist_ok=True)

    primary_path = save_skill(skill_suite.primary.content, repo_name, output_dir)
    companion_entries: list[dict[str, str]] = []
    for artifact in skill_suite.companions:
        artifact_dir = root / _make_skill_name(artifact.name)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = artifact_dir / "SKILL.md"
        artifact_path.write_text(artifact.content)
        companion_entries.append(
            {
                "name": artifact.name,
                "description": artifact.description,
                "role": artifact.role,
                "path": str(artifact_path.relative_to(root)),
            }
        )

    manifest = {
        "source_repo": skill_suite.source_repo,
        "target_repo": skill_suite.target_repo,
        "primary": {
            "name": skill_suite.primary.name,
            "description": skill_suite.primary.description,
            "role": skill_suite.primary.role,
            "path": str(primary_path.relative_to(root)),
        },
        "companions": companion_entries,
    }
    manifest_path = root / "skill-suite.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return manifest_path
