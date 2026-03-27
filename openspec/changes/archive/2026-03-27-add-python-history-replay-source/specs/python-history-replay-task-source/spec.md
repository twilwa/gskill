## ADDED Requirements

### Requirement: The system SHALL collect Python history-replay tasks from git history

The system SHALL support a Python-focused repo-native task source that mines candidate fix commits from a repository checkout, validates them by reversing the fix into a broken snapshot, and emits canonical tasks only when the repository verifier fails from a passing baseline.

#### Scenario: Validated fix commits become canonical tasks
- **WHEN** the history-replay source finds a supported Python fix commit and the verifier passes before the fix is reversed and fails after the reversal
- **THEN** the source SHALL emit a canonical local-checkout task that references the broken snapshot, the verifier command, and commit provenance

#### Scenario: Unsupported repositories fail clearly
- **WHEN** the history-replay source cannot infer a supported Python validation command or cannot find valid replayable fix commits
- **THEN** the source SHALL fail with a clear source-specific error instead of emitting empty or unverifiable tasks

### Requirement: History-replay tasks SHALL preserve fix provenance

The system SHALL preserve enough commit metadata for operators to understand which fix produced each task and which history strategy produced the bundle.

#### Scenario: Task metadata records replayed commit information
- **WHEN** the history-replay source emits a canonical task
- **THEN** the task metadata SHALL include the fixed commit hash, parent hash, commit subject, and changed paths used to build the replay task

#### Scenario: Reports identify history-source provenance
- **WHEN** a run uses the Python history-replay source
- **THEN** the task bundle provenance in the run report SHALL identify the source as history replay and record the repository URL or checkout context used to mine commits
