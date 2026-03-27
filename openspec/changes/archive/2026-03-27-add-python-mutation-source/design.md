## Context

`gskill` now has a canonical task abstraction, but only one concrete source: SWE-smith. That means every optimization task still depends on an external benchmark dataset and a SWE-bench-specific Docker execution path. The next useful step is a repo-native source that can produce real repair tasks from the target repository itself.

The narrowest realistic source is Python-only. This repository is Python, the current validation stack already assumes Python in several places, and `mini-swe-agent` exposes a local environment that can run against a real checkout without additional infrastructure.

## Goals / Non-Goals

**Goals:**
- Add a Python mutation source that can collect canonical tasks from a repository checkout.
- Support local-checkout task execution in the evaluator so generated tasks are actually optimizable.
- Keep the new source deterministic enough for tests and clear enough to extend later.
- Preserve the existing SWE-smith default path.

**Non-Goals:**
- Generalize mutation generation across all languages.
- Build a full task-quality scoring pipeline or semantic deduplication system.
- Implement history replay, PR mining, or non-Python repo-native sources in this change.

## Decisions

### Introduce a task-source request object

Sources need more than a repo slug once they become repo-native. This change will introduce a request object that carries the repo name, repo URL, task limit, and a scratch location for source-specific materialization.

Alternative considered:
- Thread `repo_url` and scratch paths through optional keyword arguments.

Why not:
- That would make the interface unstable as more sources arrive.

### Keep the first mutation source Python-only

The source will scan Python implementation files, apply small AST-safe mutations, and keep only mutations that make the repository's validation command fail from a passing baseline.

Alternative considered:
- Attempt language-agnostic textual mutations immediately.

Why not:
- That would create low-signal tasks and a larger invalid-task surface before the source pipeline is proven.

### Use repository snapshots plus local-checkout execution

Each accepted mutation task will reference a prepared checkout snapshot. The evaluator will copy that snapshot into a temp worktree, run `mini-swe-agent` in a local environment, and verify the resulting patch with the task's shell command.

Alternative considered:
- Reuse the current SWE-bench Docker path by translating local tasks into fake SWE-bench records.

Why not:
- That would preserve the coupling the task-source layer was meant to remove.

### Start with conventional Python validation-command discovery

The source will infer a verification command from common Python repository conventions such as `pyproject.toml`, `pytest.ini`, and `tests/`. If no supported command can be inferred, the source should fail clearly instead of synthesizing low-confidence tasks.

Alternative considered:
- Require a user-provided command for every mutation run.

Why not:
- The first repo-native source should still be automatable for common Python repositories.

## Risks / Trade-offs

- [Mutation heuristics may produce brittle or trivial tasks] → Restrict the first implementation to a small set of reversible AST mutations and require a failing verifier from a passing baseline.
- [Local execution can be slower and less isolated than SWE-bench Docker] → Keep timeouts explicit and run verification in a fresh copy of the mutated snapshot.
- [Repository command discovery may fail on unconventional repos] → Fail clearly and leave room for later explicit command configuration.
- [Python-only scope may look narrow] → Document it as the first repo-native source, not the final architecture.

## Migration Plan

1. Add task-source request plumbing and the Python mutation source implementation.
2. Add a local-checkout runner path in the evaluator.
3. Expose the source in CLI/task-bundle reporting.
4. Cover source collection and local runner behavior with regression tests.

Rollback is straightforward because the existing SWE-smith source remains the default and the new source is opt-in.

## Open Questions

- Should accepted mutation snapshots be persisted under `scratchpad/` for inspection, or remain purely temporary for now?
- Should command discovery support `mise run test` before direct `uv run pytest`, or should that wait until command inference is more configurable?
