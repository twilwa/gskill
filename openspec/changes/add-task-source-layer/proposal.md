## Why

`gskill` currently learns against a single hard-coded SWE-smith adapter. That makes arbitrary repository targets a dead end, mixes benchmark concerns with repo-native task generation, and blocks later work on richer backends such as Shinka-style evolutionary search.

## What Changes

- Introduce a canonical task model that separates problem statements, runtime environment, verification, provenance, and source-specific metadata.
- Replace the direct SWE-smith loader with a named task-source layer that can assemble task bundles from one or more sources.
- Refactor the optimization pipeline to consume canonical task bundles instead of raw SWE-smith records.
- Preserve the current SWE-smith path as the first source adapter so existing workflows continue to work while new sources are added later.
- Add source-aware splitting and reporting so task provenance, bundle composition, and rejected tasks remain visible during optimization.

## Capabilities

### New Capabilities
- `task-source-layer`: Build optimization-ready task bundles from named task sources through a canonical task model.

### Modified Capabilities
- None.

## Impact

- Affected code: `main.py`, `src/tasks.py`, `src/pipeline.py`, `src/evaluator.py`, and the task-related tests.
- Affected behavior: task selection and evaluation setup for `gskill run`, plus run-report contents.
- Dependencies: no new runtime dependency is required for the foundation change.
