## Purpose

Define the canonical task preview CLI behavior for inspecting task bundles produced by the task-source layer, including repo-native source context and human-readable summaries.

## Requirements

### Requirement: The task preview CLI MUST use canonical task sources

The `gskill tasks` command MUST preview canonical task bundles produced by the registered task-source layer rather than reading raw SWE-smith rows directly.

#### Scenario: Default preview uses the canonical SWE-smith source
- **WHEN** a user runs `gskill tasks pallets/jinja --limit 10`
- **THEN** the command builds a canonical task bundle with the default `swe-smith` source
- **AND** it writes a JSON artifact that includes bundle provenance and serialized canonical tasks.

### Requirement: The task preview CLI MUST accept repo-native source context

The preview command MUST allow users to supply repository-location context when previewing repo-native sources.

#### Scenario: Preview a repo-native source from a local checkout
- **GIVEN** a local checkout path `/tmp/repo`
- **WHEN** a user runs `gskill tasks acme/repo --task-source python-history-replay --checkout-path /tmp/repo`
- **THEN** the command passes the repo name and checkout path into canonical task-bundle construction
- **AND** the output JSON includes repo-native task metadata and provenance.

### Requirement: List mode MUST print the selected task summaries

The preview command MUST make `--list` produce a concise human-readable summary of the tasks it selected.

#### Scenario: List mode prints canonical task summaries
- **WHEN** a user runs `gskill tasks pallets/jinja --limit 2 --list`
- **THEN** stdout includes both selected task ids
- **AND** each summary identifies the task source and family
- **AND** the command still writes the JSON artifact.
