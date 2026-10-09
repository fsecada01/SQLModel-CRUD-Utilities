# 0008. Keep v0.2.0 additive and backward compatible

- Status: accepted
- Date: 2026-02-16

## Context
v0.2.0 added several features on top of a published v0.1.0.

## Decision
No breaking changes: all new features are opt-in. Mixins apply only when inherited, transaction managers are optional, and the exception classes are not raised by the existing CRUD functions. The design also promised that exception raising defaults to off and that hooks run only when registered; neither a `raise_on_error` parameter nor hooks were implemented (see [ADR-0002](0002-use-custom-exception-hierarchy.md) and [ADR-0006](0006-add-lifecycle-hooks.md)). The release summary records no new dependencies, optional `loguru` support maintained, and Python 3.9+ support.

## Consequences
- Later breaking changes (for example positional-argument reordering) need to be called out in the CHANGELOG and versioned accordingly.
