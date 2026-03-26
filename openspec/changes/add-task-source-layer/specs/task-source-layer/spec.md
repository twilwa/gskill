## ADDED Requirements

### Requirement: Canonical tasks SHALL describe optimization work independently from the source dataset

The system SHALL represent optimization tasks through a canonical task model that separates the task prompt, runtime environment, verification strategy, provenance, and source-specific metadata.

#### Scenario: SWE-smith records are converted into canonical tasks
- **WHEN** the system loads tasks for a repository through the SWE-smith adapter
- **THEN** each returned task SHALL include a canonical identifier, problem statement, environment description, verifier description, source name, and source metadata

#### Scenario: Canonical tasks retain provenance for reporting
- **WHEN** a task bundle is assembled
- **THEN** each task SHALL preserve the source name and sufficient provenance metadata to explain where the task came from in later reports

### Requirement: The pipeline SHALL build task bundles from named task sources

The system SHALL collect tasks through named task sources rather than calling a dataset-specific loader directly, and it SHALL assemble those tasks into a canonical task bundle before optimization begins.

#### Scenario: Default task loading uses the registered SWE-smith source
- **WHEN** a user runs `gskill run` without overriding task-source settings
- **THEN** the pipeline SHALL build its task bundle through the registered SWE-smith source

#### Scenario: Explicit task-source selection is validated
- **WHEN** a user selects a task source or task profile that is not registered
- **THEN** the command SHALL fail with a clear validation error before optimization starts

### Requirement: Task bundles SHALL expose source-aware train, validation, and test splits

The system SHALL split canonical task bundles into train, validation, and test partitions without requiring downstream code to understand source-specific record formats.

#### Scenario: Bundle consumers receive canonical split outputs
- **WHEN** the pipeline prepares work for optimization
- **THEN** it SHALL consume train, validation, and test splits from the task bundle rather than slicing raw source records directly

#### Scenario: Run reports summarize bundle composition
- **WHEN** a run report is written after a seed generation or optimization run
- **THEN** the report SHALL include task-source provenance for the bundle, including which sources contributed tasks and how many tasks each source contributed

### Requirement: Canonical tasks SHALL be executable through a source-neutral evaluation boundary

The system SHALL evaluate candidate skills against canonical tasks through a task-runner boundary instead of depending on raw SWE-smith task dictionaries throughout the evaluator path.

#### Scenario: SWE-smith tasks continue to run through the new boundary
- **WHEN** a canonical task originates from the SWE-smith source
- **THEN** the evaluator SHALL execute the task successfully through the source-neutral evaluation boundary

#### Scenario: Missing runner support fails clearly
- **WHEN** a canonical task references an unsupported environment or verifier kind
- **THEN** the evaluator SHALL fail the task with a clear unsupported-runner reason instead of raising an unhandled exception
