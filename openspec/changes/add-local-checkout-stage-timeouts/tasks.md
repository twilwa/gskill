## 1. Specification

- [x] 1.1 Draft proposal, design, and spec delta for stage-specific local-checkout timeouts.

## 2. Implementation

- [x] 2.1 Add canonical parsing for local-checkout stage timeout metadata with compatibility fallbacks.
- [x] 2.2 Apply stage-specific timeout budgets inside the local-checkout evaluator path.

## 3. Validation

- [x] 3.1 Add regression tests for stage timeout attribution and legacy timeout fallback behavior.
- [x] 3.2 Run `uv run pytest`, `uv run ruff check .`, and `mise exec -- openspec validate add-local-checkout-stage-timeouts`.
