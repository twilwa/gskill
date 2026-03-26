## ADDED Requirements

### Requirement: The system SHALL collect Python mutation tasks from a repository checkout

The system SHALL support a Python-focused repo-native task source that clones or materializes a target repository checkout, applies candidate Python source mutations, and emits canonical tasks only when the repository's verifier fails from a passing baseline.

#### Scenario: Validated mutations become canonical tasks
- **WHEN** the Python mutation source finds a supported Python mutation and the repository verifier passes before the mutation and fails after the mutation
- **THEN** the source SHALL emit a canonical task that references the mutated repository snapshot, the verifier command, and mutation provenance

#### Scenario: Unsupported repositories fail clearly
- **WHEN** the Python mutation source cannot infer a supported Python validation command or cannot find valid Python mutation candidates
- **THEN** the source SHALL fail with a clear source-specific error instead of emitting empty or unverifiable tasks

### Requirement: Canonical local-checkout tasks SHALL execute through a local runner

The system SHALL execute canonical tasks backed by repository snapshots through a local-checkout runner rather than requiring SWE-bench Docker metadata.

#### Scenario: Local-checkout tasks run in a copied repository snapshot
- **WHEN** the evaluator receives a canonical task with a local-checkout environment and a shell-command verifier
- **THEN** it SHALL copy the referenced snapshot into a temp working directory, run the coding agent there, and verify the resulting patch with the task's verifier command

#### Scenario: Unsupported local task kinds fail safely
- **WHEN** the evaluator receives a local-checkout canonical task whose verifier kind or environment kind is unsupported
- **THEN** it SHALL return a failed evaluation with a clear unsupported-runner reason instead of raising an unhandled exception

### Requirement: Task-source collection SHALL accept repository location context

The system SHALL pass repository location context to task sources so repo-native sources can materialize and inspect the target repository instead of relying only on a repo slug.

#### Scenario: Pipeline passes repository URL into source collection
- **WHEN** a user runs `gskill run` with a repo URL and selects the Python mutation source
- **THEN** the pipeline SHALL provide the repository URL and repo name to task-source collection for that source

#### Scenario: Reports identify repo-native mutation task provenance
- **WHEN** a run uses the Python mutation source
- **THEN** the run report SHALL include mutation-source provenance for the resulting task bundle
