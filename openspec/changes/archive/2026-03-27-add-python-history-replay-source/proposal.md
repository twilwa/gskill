## Why

`gskill` can now generate repo-native Python mutation tasks, but those tasks are still synthetic. The next useful step is to replay real repository history so the optimizer can learn from actual bug-fix commits rather than only invented regressions.

## What Changes

- Add a Python git-history replay task source that mines candidate fix commits from a repository checkout.
- Build canonical local-checkout tasks by reversing validated fix commits into broken snapshots and asking the agent to restore the fix.
- Record history-source provenance so run reports show which repository history and commit metadata produced the task bundle.
- Add regression coverage and docs for the new source.

## Capabilities

### New Capabilities
- `python-history-replay-task-source`: Generate repo-native repair tasks from validated Python fix commits in git history.

### Modified Capabilities
- None.

## Impact

- Affected code: `src/tasks.py`, `README.md`, `main.py`, and task/pipeline tests.
- Affected behavior: `gskill run` can opt into a repo-native history-replay source that emits canonical local-checkout tasks from git history.
- Dependencies: no new third-party dependency is required; the implementation reuses `git`, the existing Python verifier discovery, and the local-checkout runner already present in the evaluator.
