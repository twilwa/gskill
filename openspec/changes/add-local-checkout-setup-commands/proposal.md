## Why

`gskill` now emits repo-native `local_checkout` tasks, but the evaluator still ignores `EnvironmentSpec.setup_commands` and `install_commands` when it verifies those tasks. That leaves the local-checkout environment contract partially implemented and makes repo-native tasks fragile for repositories that need bootstrap steps before tests can run.

## What Changes

- Teach the local-checkout evaluator path to read and execute setup and install commands from canonical task environments.
- Preserve failure reasons for setup, install, patch-apply, and verifier stages so run reports stay diagnosable.
- Add regression coverage for command ordering and failure handling.

## Capabilities

### Modified Capabilities
- `local-checkout-evaluation`: Local-checkout verification now honors declared environment bootstrap commands before running the verifier.

## Impact

- Affected code: `src/evaluator.py` and evaluator tests.
- Affected behavior: repo-native tasks can declare environment bootstrap commands and expect them to be executed during verification.
- Dependencies: none.
