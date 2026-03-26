## Context

The local-checkout evaluator currently resolves one timeout value from task metadata and reuses it for:
1. patch apply,
2. setup commands,
3. install commands,
4. verifier commands.

This is adequate for simple tasks, but it becomes brittle as repo-native tasks get more realistic. Setup and install are often slower and less deterministic than the verifier itself, and a single shared timeout does not communicate where the budget was intended to be spent.

## Goals / Non-Goals

**Goals:**
- Support stage-specific timeouts for local-checkout evaluation.
- Preserve backward compatibility for tasks that only specify the existing shared timeout fields.
- Keep failure reasons stage-specific and stable.

**Non-Goals:**
- Change SWE-bench Docker timeout handling.
- Infer timeouts from repository contents.
- Add new task sources in the same delta.

## Decisions

### Represent stage-specific timeouts in task metadata first

The canonical task dataclasses already expose one environment timeout and one verifier timeout. Rather than widen those dataclasses immediately, the smallest next step is to carry stage-specific timeout values in local-checkout task metadata under a dedicated key, while preserving the existing top-level timeout fields as fallbacks.

### Resolve timeout budgets by stage with clear fallback order

The evaluator will resolve timeouts in this order:

- patch apply:
  1. local-checkout metadata patch timeout
  2. environment timeout
  3. default local timeout

- setup:
  1. local-checkout metadata setup timeout
  2. environment timeout
  3. default local timeout

- install:
  1. local-checkout metadata install timeout
  2. environment timeout
  3. default local timeout

- verifier:
  1. local-checkout metadata verifier timeout
  2. verifier timeout
  3. environment timeout
  4. default local timeout

This keeps existing tasks working while allowing finer control for newer sources.

### Preserve current failure reasons

Timeouts should still surface as:
- `patch_apply_timeout`
- `setup_timeout`
- `install_timeout`
- `shell_command_timeout`

The change is in budget assignment, not in the external failure vocabulary.

## Risks / Trade-offs

- Metadata-based stage timeouts are less explicit than a wider canonical dataclass API.
- Repo-native task sources may need follow-up work to emit stage-specific values once the evaluator supports them.

## Migration Plan

1. Add metadata parsing helpers for local-checkout stage timeouts.
2. Apply those budgets in the evaluator with fallback to existing shared timeouts.
3. Add regression tests for setup/install/verifier timeout attribution and fallback compatibility.
