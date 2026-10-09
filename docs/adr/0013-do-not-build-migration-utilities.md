# 0013. Do not build migration utilities

- Status: accepted
- Date: 2026-10-09

## Context
ADR-0007 deferred migration utilities and called them out of scope. Issue #26 (v0.4.0 Phase 4, epic #28) asks for a decision to build them or to close the item as out of scope.

This library is a small set of CRUD helpers returning `(success, data)` tuples over a caller-supplied `Session` or `AsyncSession`. It owns no engine, no metadata and no schema. Schema migration for SQLModel/SQLAlchemy projects is already served by Alembic, which is mature, autogenerates from `SQLModel.metadata`, handles dialect differences, and has its own versioning and downgrade model. Any utility built here would either wrap Alembic (a new dependency, or an optional extra that adds little over calling Alembic directly) or reimplement a fragile subset of it (diffing metadata, emitting DDL, tracking revision state).

The mixins shipped in v0.2.0 add columns to user models, so migrations for them are the user's Alembic concern like any other model change. Nothing in the library creates a gap that a migration helper would fill.

## Decision
We will not build migration utilities. ADR-0007's "migrations are out of scope" stance stands for this item, now with the reasons recorded here. ADR-0007 is superseded by this ADR for the migration utilities item only; its other deferred items are unaffected. Issue #26 closes as out of scope with no code, tests, CHANGELOG entry or docs regeneration.

## Consequences
- No new public API, dependency or optional extra; sync/async parity is unaffected.
- Users keep using Alembic directly; documentation may point there if users ask.
- Revisit only with a concrete, library-specific need that Alembic cannot meet, for example a helper that must know about this library's mixins. That would need a new ADR with a scoped design.

## Alternatives considered
- Thin Alembic wrapper (optional extra): rejected, it adds a surface to maintain and version-track without capability beyond Alembic's own API.
- Own schema diff/DDL utilities: rejected, high risk and effort, duplicates Alembic, and is outside a CRUD helper's purpose.
- Documentation-only recipe for Alembic with the mixins: not rejected on merit but outside this issue's checklist; noted as a possible follow-up.
