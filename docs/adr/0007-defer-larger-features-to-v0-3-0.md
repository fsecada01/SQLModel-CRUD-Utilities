# 0007. Defer larger features to v0.3.0

- Status: accepted (GraphQL item superseded by 0014)
- Date: 2026-02-16

## Context
The v0.2.0 quick-start guide wanted to keep release scope manageable.

## Decision
The query builder, caching layer, change tracking, migration utilities and GraphQL support are out of v0.2.0 and deferred to v0.3.0 or later. The stated reasons are: the query builder is complex and needs more design, caching needs external dependencies, change tracking is complex, migrations are out of scope, and GraphQL is a different domain.

## Consequences
- The design document sketched a `QueryBuilder` and a pooled-engine helper; neither was adopted.
- Revisit any of these with a new ADR before building it.
