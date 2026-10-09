# 0014. Do not build GraphQL support

- Status: accepted
- Date: 2026-10-09

## Context
ADR-0007 deferred GraphQL support because it is "a different domain".
Issue #27 (v0.4.0 epic #28) asks for a build-or-close decision: either a
scoped design behind a `[graphql]` extra, or a recorded decision not to
build it. The epic title ("build out") is not a reason to build.

This library is a set of helpers over a SQLModel `Session` or
`AsyncSession`. Every function returns `(success, data)` and has a sync and
an async twin with matching signatures, enforced by
`tests/test_sync_async_parity.py`.

## Decision
We do not build GraphQL support. #27 closes with this ADR and no code.

Reasons:
- GraphQL is a transport and schema layer. The CRUD helpers are already
  plain functions that any resolver can call, so there is no capability gap
  a GraphQL module would fill.
- Any integration must pick a framework (Strawberry, Graphene, Ariadne),
  each with its own type system and context conventions. Choosing one
  couples the library to that framework's release cycle for a feature with
  no demonstrated demand (no issue, user request or internal consumer).
- A useful integration means generating GraphQL types and resolvers from
  SQLModel models, which is a code-generation and schema-design project,
  not a CRUD helper. It would also need its own sync/async parity story
  across the framework's resolver model.
- The `(success, data)` contract does not map onto GraphQL's error model
  without a policy decision (raise, return union types, or populate
  `errors`) that belongs to the application.

## Consequences
- ADR-0007's GraphQL item is superseded by this ADR; its other deferred
  items are unaffected.
- No `[graphql]` extra, no new dependency, no public API change.
- Applications use the existing helpers inside their own resolvers.
- Revisit with a new ADR only if there is concrete demand and a named
  framework; a `docs/` recipe showing resolver usage is a lighter option to
  consider first.

## Alternatives considered
- A `[graphql]` extra with Strawberry integration: rejected for the framework
  coupling and unproven demand described above.
- Framework-agnostic resolver helpers: rejected, they would only rename
  calls to the existing functions.
