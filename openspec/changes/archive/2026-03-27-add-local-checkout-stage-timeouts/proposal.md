## Why

`gskill` now honors local-checkout setup and install commands, but the evaluator still uses a single timeout budget for patch apply, setup, install, and verifier execution. That means a slow bootstrap step can consume the entire budget before the verifier starts, and the resulting failure mode depends more on incidental timing than on the task contract.

## What Changes

- Extend canonical local-checkout task metadata so timeout intent can be expressed per stage.
- Teach the evaluator to apply stage-specific timeout budgets for patch apply, setup, install, and verifier execution.
- Add regression coverage for timeout attribution and fallback behavior when only the legacy shared timeout is present.

## Capabilities

### Modified Capabilities
- `local-checkout-evaluation`: Local-checkout verification now enforces timeout budgets per execution stage instead of sharing one budget across the full pipeline.

## Impact

- Affected code: `src/tasks.py`, `src/evaluator.py`, and evaluator/task tests.
- Affected behavior: repo-native local-checkout tasks get more predictable timeout behavior and clearer failure reasons.
- Dependencies: none.
