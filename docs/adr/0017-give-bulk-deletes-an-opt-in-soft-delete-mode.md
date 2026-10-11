# 0017. Give bulk deletes an opt-in soft-delete mode and correct the mixin docs

- Status: accepted (amends 0004, 0005, 0011 and 0012)
- Date: 2026-10-10

## Context
Issue #51, raised while reviewing #41. The ID-list bulk helpers (`delete_rows_within_id_list` and `bulk_update_rows`, added in #12; they have no ADR of their own, so their contract is spread over ADR-0011, ADR-0012 and the docstrings) send Core statements. Two things about how they meet the mixins were wrong or undecided.

Verified on SQLite with real sessions, sync and async:
- `delete_rows_within_id_list` on a `SoftDeleteMixin` model issues a hard `DELETE`: the row is gone and the mixin is never consulted.
- `bulk_update_rows` on an `AuditMixin` model refreshes `updated_at`. `AuditMixin.updated_at` is declared with `sa_column_kwargs={"onupdate": ...}`, and a column-level `onupdate` fires for a Core `UPDATE`, exactly as `TimestampMixin.updated_at` does. `updated_by` has no default and is only written when the caller names it in `data`.
- `created_at` / `created_by` are insert-time values; they only matter to inserts and are not touched by either helper.

The docstrings of `bulk_update_rows` (sync and async) said `AuditMixin.updated_at` is not refreshed, and then in the same sentence that column-level `onupdate` defaults do fire. ADR-0004 repeated the wrong claim in its Consequences, and `CLAUDE.md` said the bulk helpers bypass "Python-side column defaults".

## Decision
Additive and backward compatible; no default changes.

### Correct the documentation
State the verified behaviour everywhere it was misstated: a bulk write fires column-level `onupdate` defaults, so `updated_at` is refreshed for both `TimestampMixin` and `AuditMixin`; `updated_by` and the `SoftDeleteMixin` fields are not set unless the caller supplies them; ORM events and change tracking (ADR-0011) do not see bulk writes. The docstrings of `bulk_update_rows` / `a_bulk_update_rows`, ADR-0004, ADR-0005, `CLAUDE.md`, the README and the mixin docstrings are updated. `bulk_upsert_mappings` did not repeat the claim and is unchanged.

### `soft` and `deleted_by` on `delete_rows_within_id_list`
Append two keyword parameters to `delete_rows_within_id_list` and `a_delete_rows_within_id_list`, after the existing ones, with identical signatures:

- `soft: bool = False`. `False` is today's hard `DELETE`, unchanged.
- `deleted_by: str | None = None`.

With `soft=True` the helper runs a chunked Core `UPDATE` in one transaction that does what `SoftDeleteMixin.soft_delete(user)` does: `is_deleted = True`, `deleted_at` = the mixin's own UTC-now helper (one value for the whole call, whatever the chunking), `deleted_by` = the given user (`None` when not given, as the mixin does).

- Rows that are already soft-deleted are excluded in the `WHERE` (`is_deleted` false or NULL), so their original `deleted_at` / `deleted_by` survive.
- The returned count is the number of rows newly marked deleted. Rows already soft-deleted and IDs with no row are not counted. This is the same "rows affected" meaning the hard path has, and unlike `bulk_update_rows`, which counts rows matched. A second identical call returns `(True, 0)`.
- Chunking (`chunk_size`), the single transaction, rollback-and-reraise on error, and cache invalidation (a soft delete is a write, so the model's cache entries are dropped after the commit, ADR-0012) behave exactly as on the hard path. The statement is the ORM-enabled `UPDATE`, so instances of the model already loaded in the session are synchronised by SQLAlchemy.
- `AuditMixin` / `TimestampMixin` `updated_at` fires through `onupdate`; `updated_by` is not set. Bulk soft delete is not recorded by change tracking.
- Validation runs before anything is sent: `soft=True` on a model that lacks any of `is_deleted`, `deleted_at`, `deleted_by` raises `ValueError` naming the missing columns; `deleted_by` with `soft=False` raises `ValueError`. All three columns are required, mirroring the mixin, rather than writing a subset.
- `pk_field` keeps its meaning: it names a single primary-key column and every row whose value is in the list is matched. For a composite key that can be several rows per ID, as it already can for the hard delete.

### No automatic `updated_by` in `bulk_update_rows`
The "fill `updated_by` / `deleted_by` from a caller-supplied value" question is resolved as documented behaviour: pass `updated_by` in `data`. `deleted_by` is the explicit parameter above. `bulk_update_rows` gets no new parameter.

## Consequences
- Callers who want bulk soft delete have a supported path instead of a hand-written `bulk_update_rows(ids, {"is_deleted": True, ...})`, and the two cannot drift from `SoftDeleteMixin`'s field semantics because the helper builds them in one place (`utils.soft_delete_statement`).
- Existing callers see no change: the default is still a hard delete. A caller who has a `SoftDeleteMixin` model and expected the mixin to apply to the bulk helper must now opt in; the docstring says so first.
- `get_rows` still does not exclude soft-deleted rows (ADR-0005); callers filter on `is_deleted`.
- The soft path adds one `WHERE` predicate. On a large table an index on `is_deleted` (the mixin already creates one) keeps it cheap.
- There is still no bulk `restore`. `bulk_update_rows(ids, {"is_deleted": False, "deleted_at": None, "deleted_by": None})` does it. Revisit if that is asked for.
- Soft delete does not honour the `max_length=100` of `deleted_by` in Python; a backend that enforces `VARCHAR(100)` raises on the oversized value and the call rolls back.

## Alternatives considered
- Keep the hard delete and only document it: simplest, but leaves every `SoftDeleteMixin` user to rebuild the soft delete themselves with `bulk_update_rows`, each with their own timestamp and `deleted_by` handling.
- Soft-delete automatically for models that use `SoftDeleteMixin`: rejected. It silently changes what an existing call does to existing data (rows stop being removed, disk is not reclaimed, unique constraints still hold the deleted rows), and this library keeps additions opt-in and backward compatible (as in ADR-0008).
- A separate function (`soft_delete_rows_within_id_list`): rejected for a parameter, matching the issue's option (c) and keeping one entry point for "delete these IDs" with the same chunking, validation and cache behaviour.
- Fill `updated_by` in `bulk_update_rows` from a new parameter: deferred. `data` already carries it, a new parameter would be a second way to say the same thing, and `bulk_update_rows` writes arbitrary columns for which "who updated" is not always one string.
- Tolerate partial `SoftDeleteMixin` columns (write only the ones that exist): rejected as a quiet half soft delete; the missing columns are named in the error instead.
