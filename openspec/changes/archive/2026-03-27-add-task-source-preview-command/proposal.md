## Why

`gskill` can now build canonical task bundles from both benchmark-backed and repo-native task sources, but the `gskill tasks` CLI still reads raw SWE-smith rows directly. That makes the preview command inconsistent with the actual optimization pipeline and leaves no way to inspect repo-native `local_checkout` tasks before starting a full run.

## What Changes

- Route `gskill tasks` through canonical task-bundle construction instead of the legacy SWE-smith-only loader.
- Add task-source selection and repo-location options so the preview command can inspect repo-native sources.
- Make the preview output serialize canonical bundle provenance and task metadata, and make `--list` print concise task summaries to stdout.

## Capabilities

### Modified Capabilities
- `task-preview-command`: The task preview CLI now reflects the same canonical task-source pipeline that `gskill run` uses.

## Impact

- Affected code: `main.py`, task-preview tests, and README usage docs.
- Affected behavior: users can preview canonical tasks from any registered source, including repo-native sources that need a checkout path or repo URL.
- Dependencies: none.
