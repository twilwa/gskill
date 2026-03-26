## Context

The canonical task model already distinguishes three parts of task execution:
- environment setup commands
- environment install commands
- verifier commands

That distinction exists in `EnvironmentSpec`, but the local-checkout evaluator currently skips the first two parts and runs only the verifier commands against a copied snapshot. This worked for the first repo-native sources because they were intentionally simple, but it leaves the contract incomplete and weakens future task generation.

## Goals / Non-Goals

**Goals:**
- Honor `setup_commands` and `install_commands` for local-checkout verification.
- Keep command execution deterministic and observable in failure reasons.
- Preserve the existing verifier-copy isolation model.

**Non-Goals:**
- Add dependency inference or task-source-specific bootstrap logic.
- Change the canonical task model.
- Rework the Docker SWE-bench path.

## Decisions

### Execute commands in environment order before verifier commands

The evaluator will run local-checkout commands in this order:
1. apply the candidate patch into a copied snapshot,
2. run setup commands,
3. run install commands,
4. run verifier commands.

This keeps the bootstrap steps aligned with the patched checkout and allows future tasks to mutate files that install steps may read.

### Fail early with stage-specific reasons

The evaluator will stop at the first failing stage and return a reason that identifies whether setup, install, patch apply, or verifier execution failed. This preserves enough information for debugging generated tasks and evaluator regressions.

### Reuse the existing shell runner instead of adding a new execution layer

The evaluator already has a shell-script helper with timeout handling and logging. The new behavior will reuse that helper instead of adding another subprocess abstraction.

## Risks / Trade-offs

- Additional command execution increases verification time for local-checkout tasks.
- Command ordering is now part of the contract and should stay stable.
- Setup or install commands may create more non-source files in snapshots, so the evaluator must continue using throwaway verification copies.

## Migration Plan

1. Read setup and install commands from local-checkout task environments.
2. Execute them in the copied verification checkout before verifier commands.
3. Add regression tests for successful command sequencing and failure propagation.

Rollback is straightforward because the behavior is isolated to the local-checkout evaluator path.
