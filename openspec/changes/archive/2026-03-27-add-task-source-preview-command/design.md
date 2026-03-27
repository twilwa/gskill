## Context

The current `gskill tasks` command predates the canonical task-source layer. It only calls `load_tasks()`, which means:
- previews are limited to raw SWE-smith rows,
- task-source selection is ignored,
- repo-native sources cannot be inspected, and
- the command output does not match the bundle shape consumed by `gskill run`.

That mismatch is now more costly because repo-native task generation is part of the normal workflow.

## Goals / Non-Goals

**Goals:**
- Preview canonical task bundles from the same registered sources used by the optimization pipeline.
- Let users pass enough repository context to preview repo-native sources.
- Keep the command simple: one JSON artifact plus an optional stdout listing.

**Non-Goals:**
- Change how `gskill run` builds or evaluates tasks.
- Add new task sources.
- Add interactive filtering or rich TUI output.

## Decisions

### Reuse canonical task-bundle construction

The preview command will call `build_task_bundle()` so the preview path and the optimization path stay aligned. The preview command will use the same repo-name extraction logic already used by the pipeline.

### Accept repo-native location context explicitly

Repo-native previews need a real repository location. The CLI will accept:
- a positional repo identifier that may be either `owner/repo` or a GitHub URL,
- `--checkout-path` for an existing local checkout.

The positional value will continue to determine the canonical repo name, and it will also be forwarded as the repo URL context when it is a GitHub URL.

### Serialize the canonical bundle, not raw dataset rows

The command output file will contain the canonical bundle structure:
- bundle provenance,
- split membership,
- serialized tasks.

This makes the preview artifact directly useful for debugging task-source behavior.

### Make `--list` print concise task summaries

`--list` currently does not change behavior. After this change it will print a short, human-readable summary for each selected task while still writing the JSON artifact.

## Risks / Trade-offs

- Canonical previews may do more work than the legacy SWE-smith-only path.
- Repo-native previews can fail earlier if repository context is missing or invalid, but that failure is preferable to silently previewing the wrong source.

## Migration Plan

1. Extend the CLI command to build canonical bundles with task-source options.
2. Serialize canonical bundles to JSON.
3. Add CLI regression tests for default previews, repo-native context, and `--list`.
4. Update README examples.
