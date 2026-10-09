# 0005. Support soft delete via a mixin

- Status: accepted
- Date: 2026-02-16

## Context
The v0.1.0 library had no non-destructive deletion. The design listed soft delete as a production feature.

## Decision
`SoftDeleteMixin` adds `is_deleted`, `deleted_at` and optional `deleted_by` fields, with `soft_delete(user)` to mark a record deleted and `restore()` to undo it. Models opt in by inheriting from it. The design also proposed having `get_rows` exclude soft-deleted records by default with an override.

## Consequences
- The design advises an index on `is_deleted` and care that deleted data is not exposed in queries.
- Whether the `get_rows` exclusion shipped is not recorded in the source.
