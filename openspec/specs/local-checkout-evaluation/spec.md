## Purpose

Define how canonical local-checkout tasks are verified in copied repository snapshots, including bootstrap command execution, stage-specific timeout budgets, and stable failure reasons.

## Requirements

### Requirement: The system SHALL verify local-checkout tasks in an isolated checkout

The system SHALL verify `local_checkout` tasks in a copied snapshot and SHALL honor the canonical environment bootstrap commands before running the verifier.

#### Scenario: Setup and install commands run before verifier commands
- **WHEN** a local-checkout task includes `setup_commands`, `install_commands`, and shell-command verifier commands
- **THEN** the evaluator SHALL apply the candidate patch in a copied snapshot, run setup commands, run install commands, and then run verifier commands in that same copied snapshot

#### Scenario: Bootstrap command failures stop verification early
- **WHEN** a setup command or install command fails during local-checkout verification
- **THEN** the evaluator SHALL stop before the verifier stage and SHALL report a stage-specific failure reason

### Requirement: Local-checkout evaluation MUST enforce timeouts per stage

The local-checkout evaluator MUST assign timeout budgets independently for patch apply, setup, install, and verifier execution.

#### Scenario: Setup timeout does not consume verifier budget
- **GIVEN** a local-checkout task with distinct setup and verifier timeout settings
- **WHEN** setup exceeds its timeout budget
- **THEN** evaluation stops with `setup_timeout`
- **AND** the verifier stage does not run
- **AND** the verifier timeout remains irrelevant to that failure.

#### Scenario: Legacy shared timeout still works as fallback
- **GIVEN** a local-checkout task with only the existing environment and verifier timeout fields
- **WHEN** evaluation resolves stage budgets
- **THEN** patch apply, setup, and install fall back to the environment timeout
- **AND** the verifier falls back to verifier timeout before environment timeout.

### Requirement: Local-checkout timeout failures MUST preserve stage-specific reasons

Changing timeout budgets MUST NOT change the public timeout reason vocabulary for local-checkout evaluation.

#### Scenario: Verifier timeout remains a shell command timeout
- **WHEN** the verifier stage exceeds its timeout budget
- **THEN** the evaluator returns `shell_command_timeout`
- **AND** setup and install continue to use `setup_timeout` and `install_timeout` for their own timeout failures.
