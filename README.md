# gskill

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Claude](https://img.shields.io/badge/Claude-D97757?logo=claude&logoColor=fff)](https://claude.ai/code)
![Last Commit](https://img.shields.io/github/last-commit/twilwa/gskill)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/twilwa/gskill/pulls)

Automatically learns repository-specific skills for coding agents using evolutionary search.

Given a GitHub repository, gskill produces a skill package for agents:

- a primary workflow skill at `.claude/skills/{repo}/SKILL.md`
- a `skill-suite.json` manifest
- optional companion skills that capture transferable capabilities extracted from the source corpus

The primary workflow skill is what GEPA optimizes. Companion skills are added in a follow-up augmentation pass so the final package can tell an agent both how to work in the repo and what reusable engineering capabilities matter for that kind of work.

It implements the pipeline described in the [GEPA blog post](https://gepa-ai.github.io/gepa/blog/2026/02/18/automatically-learning-skills-for-coding-agents/), which demonstrated improvements from 24% → 93% resolve rate on some repositories.

## How it works

1. Reads a source corpus repository and generates an initial workflow skill from its README plus high-signal repo files
2. Optionally treats a different repository as the target work area via `--target-work-area`
3. Builds a canonical task bundle from one or more task sources for the target work area, passing repo-location context so repo-native sources can materialize the checkout they need
4. Uses [GEPA](https://github.com/gepa-ai/gepa)'s `optimize_anything` to iteratively refine the primary workflow skill through evolutionary search
5. Runs an augmentation pass to generate companion skills grounded in the source corpus
6. Can evaluate the best candidate on a holdout test split
7. Writes the skill suite plus a run report to disk

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- Docker (for running SWE-smith task environments)
- `OPENAI_API_KEY` set in your environment (for initial skill generation and GEPA reflection)
- `GSKILL_AGENT_MODEL` (optional) — LiteLLM model string for mini-SWE-agent (default: `openai/gpt-5.2`)

## Installation

```bash
git clone https://github.com/twilwa/gskill
cd gskill
uv sync
```

## Usage

### Run the full pipeline

```bash
uv run python main.py run https://github.com/pallets/jinja
```

This will:
- Load the default SWE-smith task source for `pallets/jinja`
- Generate an initial workflow skill
- Run up to 150 mini evaluations to optimize the workflow skill
- Write the primary skill and companion skills under `.claude/skills/jinja/`

### Common options

```bash
# Custom evaluation budget (more evals = better skill, slower run)
uv run python main.py run https://github.com/pallets/jinja --max-evals 300

# Custom output directory
uv run python main.py run https://github.com/pallets/jinja --output-dir ~/skills

# Skip static analysis, start from an empty seed
uv run python main.py run https://github.com/pallets/jinja --no-initial-skill

# Generate only the seed suite without SWE-smith optimization
uv run python main.py run https://github.com/pallets/jinja --seed-only

# Use one repo as a source corpus and a different repo as the actual work area
uv run python main.py run \
  https://github.com/twilwa/api-design-skills-package-v2 \
  --target-work-area https://github.com/twilwa/gskill \
  --seed-only

# Explicitly select task sources (repeat --task-source to combine more than one)
uv run python main.py run https://github.com/pallets/jinja --task-source swe-smith

# Use the repo-native Python mutation source
uv run python main.py run https://github.com/pallets/jinja --task-source python-mutation

# Use the repo-native Python history replay source
uv run python main.py run https://github.com/pallets/jinja --task-source python-history-replay

# Save a holdout test-set summary after optimization
uv run python main.py run https://github.com/pallets/jinja --run-test-eval --test-eval-limit 10

# Use a different model for the coding agent
uv run python main.py run https://github.com/pallets/jinja --agent-model openai/gpt-5-mini

# Use a local model (e.g. qwen2.5-coder running on localhost:11434)
OPENAI_BASE_URL=http://localhost:11434/v1 \
  uv run python main.py run https://github.com/pallets/jinja --agent-model openai/gpt-oss-120b
```

You can also set the agent model via the `GSKILL_AGENT_MODEL` environment variable instead of passing `--agent-model` every time.

### Preview available tasks

```bash
# Show the first 10 SWE-smith tasks for a repo
uv run python main.py tasks pallets/jinja

# Show more
uv run python main.py tasks pallets/jinja --limit 25
```

Task sources are selected with `--task-source`. Registered sources include `swe-smith`, `python-mutation`, and `python-history-replay`. If you do not pass the flag, `gskill` keeps using the default `swe-smith` source.

### Help

```bash
uv run python main.py --help
uv run python main.py run --help
uv run python main.py tasks --help
```

## Output

The optimized skill is written to:

```
.claude/skills/{repo}/SKILL.md
.claude/skills/{repo}/skill-suite.json
.claude/skills/{repo}/run-report.json
.claude/skills/{repo}/{companion-skill}/SKILL.md
```

The primary skill is always the root `SKILL.md`. The companion skills are additional capabilities extracted from the source corpus and listed in `skill-suite.json`.
`run-report.json` records the run configuration, task-bundle provenance, repo-location context, validation score, and optional holdout test summary.

## Task runner

A [Taskfile.yml](Taskfile.yml) provides shortcuts for common operations (requires [Task](https://taskfile.dev)):

```bash
task sync                # uv sync
task lint                # ruff check
task format              # ruff format
task test                # pytest
task run -- owner/repo   # gskill run (pass args via CLI_ARGS)
task tasks               # gskill tasks (pass args via CLI_ARGS)
```

## Project structure

```
gskill/
├── main.py              # CLI entry point (typer)
├── src/
│   ├── pipeline.py      # Top-level orchestration
│   ├── tasks.py         # Canonical task types, task sources, and bundle assembly
│   ├── evaluator.py     # mini runner + pass/fail evaluation
│   └── skill.py         # Seed generation, augmentation, and skill-suite persistence
├── Taskfile.yml         # Task runner shortcuts
└── pyproject.toml
```
