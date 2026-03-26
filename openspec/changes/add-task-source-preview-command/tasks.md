## 1. Specification

- [x] 1.1 Draft proposal, design, and spec delta for canonical task previews.

## 2. Implementation

- [ ] 2.1 Route `gskill tasks` through canonical bundle building and add repo-native preview options.
- [ ] 2.2 Serialize canonical task bundles to JSON and make `--list` print concise summaries.

## 3. Validation

- [ ] 3.1 Add CLI regression tests for default previews, repo-native context, and list output.
- [ ] 3.2 Run `uv run pytest`, `uv run ruff check .`, and `mise exec -- openspec validate add-task-source-preview-command`.
