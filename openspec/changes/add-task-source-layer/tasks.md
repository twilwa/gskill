## 1. Canonical Task Foundation

- [x] 1.1 Add canonical task types for task specs, environments, verifiers, and task bundles.
- [x] 1.2 Wrap the current SWE-smith dataset logic behind a named task-source adapter that returns canonical tasks.
- [x] 1.3 Move split construction into task-bundle assembly so downstream code no longer slices raw source records.

## 2. Pipeline And Evaluator Integration

- [x] 2.1 Refactor the pipeline to load task bundles from task sources instead of calling the SWE-smith loader directly.
- [x] 2.2 Add a task-runner boundary in the evaluator so canonical tasks can be executed without relying on raw SWE-smith dictionaries throughout the evaluation path.
- [x] 2.3 Preserve the current SWE-smith default behavior through the new source and runner boundaries.

## 3. CLI, Reporting, And Verification

- [x] 3.1 Add CLI support for selecting task sources or task profiles with validation for unknown values.
- [x] 3.2 Extend run reporting with task-source provenance and bundle-composition details.
- [x] 3.3 Add regression tests covering canonical task conversion, task bundle assembly, source selection, and SWE-smith evaluation through the new abstraction.
