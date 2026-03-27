## MODIFIED Requirements

### Requirement: The system SHALL verify local-checkout tasks in an isolated checkout

The system SHALL verify `local_checkout` tasks in a copied snapshot and SHALL honor the canonical environment bootstrap commands before running the verifier.

#### Scenario: Setup and install commands run before verifier commands
- **WHEN** a local-checkout task includes `setup_commands`, `install_commands`, and shell-command verifier commands
- **THEN** the evaluator SHALL apply the candidate patch in a copied snapshot, run setup commands, run install commands, and then run verifier commands in that same copied snapshot

#### Scenario: Bootstrap command failures stop verification early
- **WHEN** a setup command or install command fails during local-checkout verification
- **THEN** the evaluator SHALL stop before the verifier stage and SHALL report a stage-specific failure reason
