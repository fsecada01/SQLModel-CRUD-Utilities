# 0001. Export the public API from the package root

- Status: accepted
- Date: 2026-02-16

## Context
In v0.1.0 `__init__.py` was empty, so users had to import from `sqlmodel_crud_utils.sync` or `.a_sync` directly. The v0.2.0 design rated this a must-have: users should be able to import commonly used functions directly from the package.

## Decision
`sqlmodel_crud_utils/__init__.py` re-exports the sync functions under their own names and the async functions with an `a_` prefix (for example `get_row` and `a_get_row`), plus the exceptions, transaction managers and mixins, and defines `__version__` and `__all__`. The prefix avoids name clashes between the sync and async variants.

## Consequences
- Imports become `from sqlmodel_crud_utils import get_row, a_get_row`.
- Every new public function must be added to `__init__.py` and `__all__` for both variants.
- The design called for tests that verify the imports work.
