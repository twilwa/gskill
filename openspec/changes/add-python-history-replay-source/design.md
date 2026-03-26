## Context

The task-source layer now supports two classes of tasks:
- benchmark-backed SWE-smith tasks
- repo-native Python mutation tasks

That is enough to prove the architecture, but not enough to capture the most valuable repo-native signal: real fixes already merged into the repository. A narrow history-replay source is the next smallest step because it can reuse the local-checkout runner and Python verifier discovery while moving task generation closer to real maintenance work.

## Goals / Non-Goals

**Goals:**
- Add a Python-only history-replay source that mines git commits from a repository checkout.
- Turn validated fix commits into canonical local-checkout tasks.
- Keep the source deterministic enough for tests and easy to extend later.
- Preserve the existing default source behavior.

**Non-Goals:**
- Mine GitHub issues or pull requests directly.
- Generalize history replay across all languages.
- Build semantic bug-fix classification or advanced deduplication.
- Change the evaluator contract beyond what local-checkout tasks already require.

## Decisions

### Mine commits from local git history, not remote APIs

The source will inspect the repository's local git history after materialization. This keeps the implementation self-contained and avoids coupling task generation to GitHub API availability.

Alternative considered:
- Mine merged PRs or issue links from the GitHub API.

Why not:
- That is higher value long term, but it adds network and schema complexity before history replay itself is proven.

### Restrict the first replay source to Python fix commits

The source will only consider commits whose changed files include Python implementation files and whose commit message looks like a fix. This keeps candidate generation small and aligned with the existing Python verifier path.

Alternative considered:
- Replay any commit that changes files in the repo.

Why not:
- That would surface refactors, docs changes, and dependency churn that do not produce meaningful repair tasks.

### Build broken snapshots by reversing the fix commit

For each candidate fix commit, the source will:
1. materialize the repository at the fixed commit,
2. verify that the inferred Python command passes,
3. reverse-apply the commit patch into a copied snapshot,
4. keep the candidate only if the verifier now fails.

The emitted task snapshot is the reversed, broken repository state. The agent's job is to restore behavior.

Alternative considered:
- Use the parent commit directly as the broken snapshot.

Why not:
- Reversing the fix from the fixed snapshot is easier to validate and keeps the task tied to a known-good repository state with an exact patch delta.

### Capture commit metadata in task and bundle provenance

Each accepted task will include commit hash, parent hash, subject, and changed paths in metadata. The task bundle will also record source-level history provenance so reports show which repo and replay strategy generated the tasks.

Alternative considered:
- Store only the task id and snapshot path.

Why not:
- That makes generated tasks harder to inspect and compare, and weakens the report trail needed for future quality controls.

## Risks / Trade-offs

- [Commit messages are a weak fix heuristic] → Keep the heuristic small and explicit, and require verification to fail after reversal.
- [Reverse-apply may fail on some commits] → Reject those commits cleanly instead of forcing fragile tasks through.
- [History-rich repos can produce too many candidates] → Limit commit scanning and accepted tasks deterministically.
- [This overlaps with mutation-source coverage] → Preserve both sources because one is synthetic and one is grounded in real fixes.

## Migration Plan

1. Add a new task source that scans recent git history for Python fix commits.
2. Reuse the existing verifier discovery and local-checkout task model.
3. Expose the source in docs and bundle provenance.
4. Add regression tests around commit replay, provenance, and source selection.

Rollback is straightforward because the new source is opt-in and the existing sources remain unchanged.

## Open Questions

- Should commit replay prefer the repository's current default branch history only, or any reachable commit in the checkout?
- Should future history replay require changed tests in the fix commit, or is verifier failure after reversal enough for now?
