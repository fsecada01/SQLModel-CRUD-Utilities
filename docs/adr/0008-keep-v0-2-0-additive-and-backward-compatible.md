# 0008. Keep v0.2.0 additive and backward compatible

- Status: accepted
- Date: 2026-02-16

## Context
v0.2.0 added several features on top of a published v0.1.0.

## Decision
No breaking changes: all new features are opt-in. Exception raising defaults to off, hooks only run when registered, mixins apply only when inherited, and transaction managers are optional. The release summary records no new dependencies, optional `loguru` support maintained, and Python 3.9+ support.

## Consequences
- Later breaking changes (for example positional-argument reordering) need to be called out in the CHANGELOG and versioned accordingly.
