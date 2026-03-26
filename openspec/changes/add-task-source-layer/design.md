## Context

The current `gskill` pipeline assumes that every task is a SWE-smith dictionary with specific fields such as `problem_statement`, `FAIL_TO_PASS`, and `image_name`. That assumption lives in both `src/tasks.py` and `src/evaluator.py`, which means new task families cannot be added without threading more special cases through the whole stack.

The immediate goal is not to implement every future task family. The immediate goal is to create a stable task boundary that keeps the current SWE-smith workflow intact while making repo-native task generators and alternate optimization backends practical.

## Goals / Non-Goals

**Goals:**
- Introduce a canonical task model that represents optimization tasks independently from their source dataset.
- Add a task-source registry that can build a `TaskBundle` from named sources and profiles.
- Refactor the pipeline and evaluator to consume canonical tasks without regressing the current SWE-smith workflow.
- Record task provenance and bundle composition in a structured way so later source-quality work has somewhere to attach.

**Non-Goals:**
- Implement every planned repo-native source in this change.
- Replace GEPA or integrate a Shinka-style backend in this change.
- Solve long-term task quality heuristics such as semantic deduplication beyond the basic interfaces needed now.

## Decisions

### Use one canonical task type plus small supporting types

The change will add a `TaskSpec` plus supporting value types such as `EnvironmentSpec`, `VerifierSpec`, and `TaskBundle`. This keeps source-specific parsing and evaluator execution separate.

Alternative considered:
- Keep using `dict` objects with conventions.

Why not:
- That would preserve the current coupling and force each new source to emulate SWE-smith fields.

### Keep task sources thin and synchronous

Each task source will expose a small collection API that returns canonical `TaskSpec` instances. The first source will simply wrap the existing SWE-smith dataset behavior behind the new interface.

Alternative considered:
- Build a multi-stage planner/compiler/materializer pipeline immediately.

Why not:
- That is useful later, but it adds ceremony before the core abstraction is proven.

### Introduce a `TaskRunner` boundary in the evaluator path

The evaluator should stop depending on raw task dictionaries. A runner layer will translate canonical `TaskSpec` values into executable verification behavior. The first runner can still use the current mini-SWE-Agent plus Docker-based SWE-smith path.

Alternative considered:
- Keep the current evaluator and convert `TaskSpec` back into old dictionaries.

Why not:
- That would make the abstraction fake and preserve the tight coupling we are trying to remove.

### Add source selection to the CLI now

The `run` command should accept task-source configuration early, even if the only production source at first is SWE-smith. This prevents another round of CLI churn once additional sources land.

Alternative considered:
- Hide source selection until a second source exists.

Why not:
- The source layer is part of the user-facing behavior of the change, and the pipeline should be testable against explicit profiles from day one.

## Risks / Trade-offs

- [Foundation without repo-native generators may feel incomplete] -> Keep the initial source behavior unchanged and document that mutation/history sources are follow-on work enabled by this change.
- [Canonical types may drift toward internal-only complexity] -> Keep the first version minimal and add only fields already needed by the current pipeline or near-term sources.
- [Evaluator refactor could break existing SWE-smith runs] -> Preserve a dedicated SWE-smith runner path and cover it with regression tests before adding any second source.
- [CLI/source configuration could sprawl] -> Start with a small set of flags: named sources and simple profiles, not a full policy language.

## Migration Plan

1. Land the canonical task types and wrap SWE-smith behind the new source interface.
2. Refactor pipeline assembly and splitting to use `TaskBundle`.
3. Refactor evaluator execution to use canonical tasks through a runner.
4. Add CLI options and run-report provenance fields.
5. Preserve existing defaults so current users still get SWE-smith behavior without changing commands.

Rollback is straightforward because the old behavior is the first adapter. If regressions appear, the pipeline can temporarily default to the SWE-smith source only while the abstraction is fixed.

## Open Questions

- Should source grouping for train/val/test splitting live inside `TaskBundle` creation or as a separate policy object once more than one real source exists?
- Should task validation and rejection reporting be part of the source interface now, or added when the first generated repo-native source lands?
