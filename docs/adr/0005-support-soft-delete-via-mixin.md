# 0005. Support soft delete via a mixin

- Status: accepted (amended by 0017: opt-in `soft=True` on `delete_rows_within_id_list`)
- Date: 2026-02-16

## Context
The v0.1.0 library had no non-destructive deletion. The design listed soft delete as a production feature.

## Decision
`SoftDeleteMixin` adds `is_deleted`, `deleted_at` and optional `deleted_by` fields, with `soft_delete(user)` to mark a record deleted and `restore()` to undo it. Models opt in by inheriting from it. The design also proposed having `get_rows` exclude soft-deleted records by default with an override.

## Consequences
- The design advises an index on `is_deleted` and care that deleted data is not exposed in queries.
- The `get_rows` exclusion was not implemented: `sync.py` and `a_sync.py` never reference `is_deleted`, so `get_rows` returns soft-deleted rows and callers must filter them. The bulk helpers also bypass the mixin: `delete_rows_within_id_list` is a hard `DELETE` by default. ADR-0017 adds an opt-in `soft=True` / `deleted_by` mode that marks rows as `soft_delete()` does.
