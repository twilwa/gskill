## MODIFIED Requirements

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
