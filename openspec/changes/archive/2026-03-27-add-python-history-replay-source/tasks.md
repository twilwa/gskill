## 1. Spec And Source Definition

- [x] 1.1 Add the OpenSpec proposal, design, requirement delta, and task list for Python history replay.
- [x] 1.2 Register a `python-history-replay` task source without changing the default source selection.

## 2. History Replay Source

- [x] 2.1 Implement candidate commit discovery for recent Python fix commits from a repository checkout.
- [x] 2.2 Build replay tasks by reversing validated fix commits into broken snapshots from a passing baseline.
- [x] 2.3 Emit canonical task and bundle provenance with commit metadata.

## 3. Tests And Docs

- [x] 3.1 Add regression tests for history-replay collection and provenance.
- [x] 3.2 Update CLI/docs so the new source is discoverable.
- [x] 3.3 Run and record validation for the focused suite, full tests, lint, and OpenSpec.
