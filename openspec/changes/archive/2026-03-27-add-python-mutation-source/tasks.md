## 1. Spec And Source Plumbing

- [x] 1.1 Add a task-source request object so sources receive repository location context in addition to the repo name.
- [x] 1.2 Refactor the existing SWE-smith source to use the new request interface without changing default behavior.
- [x] 1.3 Add CLI and pipeline plumbing for selecting the Python mutation source.

## 2. Python Mutation Source

- [x] 2.1 Implement Python validation-command discovery for conventional Python repositories.
- [x] 2.2 Implement a small, reversible set of Python AST mutations and keep only mutations that fail verification from a passing baseline.
- [x] 2.3 Emit canonical mutation tasks with snapshot, verifier, and provenance metadata.

## 3. Local Runner And Verification

- [x] 3.1 Add evaluator support for local-checkout tasks backed by repository snapshots.
- [x] 3.2 Verify local-checkout tasks through their shell-command verifier in a fresh copied snapshot.
- [x] 3.3 Add regression tests for task-source request plumbing, mutation task collection, local runner behavior, and report provenance.
