# 0006. Add lifecycle hooks

- Status: proposed
- Date: 2026-02-16

## Context
The design wanted users to be able to inject custom logic before and after operations.

## Decision
Proposed: a `hooks.py` module with a global hook registry, calling `before_create`, `after_create`, `before_update`, `after_update`, `before_delete` and `after_delete` hooks automatically, active only when registered.

## Consequences
- No `hooks.py` exists in the package, and the v0.2.0 release summary does not list hooks as implemented, so this is unimplemented.
- The design estimated minimal overhead since hooks are optional.
