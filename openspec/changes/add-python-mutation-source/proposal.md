## Why

The new task-source layer still depends on benchmark-backed SWE-smith tasks, so `gskill` cannot yet synthesize optimization tasks from the target repository itself. A Python-focused mutation source is the smallest useful repo-native source because it can reuse the existing Python toolchain and gives `gskill` a path toward arbitrary-repo learning.

## What Changes

- Add a Python mutation task source that creates canonical tasks from a repository checkout by applying validated source-code mutations.
- Add a local-checkout task runner so canonical tasks can execute against repository snapshots without SWE-bench Docker metadata.
- Extend task-source collection so sources can receive repository location context instead of only a repo slug.
- Add mutation-source CLI support, provenance reporting, and regression coverage.

## Capabilities

### New Capabilities
- `python-mutation-task-source`: Generate repo-native Python repair tasks from validated mutations and execute them through a local-checkout runner.

### Modified Capabilities
- None.

## Impact

- Affected code: `main.py`, `src/tasks.py`, `src/pipeline.py`, `src/evaluator.py`, and task/evaluator/pipeline tests.
- Affected behavior: `gskill run` can opt into a repo-native Python mutation source and evaluate those tasks through a local runner.
- Dependencies: no new third-party dependency is required; the implementation reuses `git`, `uv`, and `mini-swe-agent`'s local environment support.
