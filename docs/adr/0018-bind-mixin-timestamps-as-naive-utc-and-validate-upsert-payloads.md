# 0018. Bind mixin timestamps as naive UTC and validate upsert payloads

- Status: accepted (amends 0004, 0005, 0012 and 0016)
- Date: 2026-10-11

## Context
Found by running the 0.4.0 candidate against `ranked_jobs_microservice` on real PostgreSQL 16 (psycopg3) before release. Three defects, none a regression of a path that consumer uses:

1. `AuditMixin.created_at` / `updated_at` and `SoftDeleteMixin.deleted_at` are annotated `datetime` with no column type, so SQLModel emits a plain `DateTime` (no time zone), but `_utc_now()` returns an aware value. Writing an aware value into a naive column is driver-defined: psycopg3 converts using the session `TimeZone` and silently shifts the stored wall-clock time (UTC 17:59 stored as 13:59 under `America/New_York`); asyncpg raises `DataError`. `soft_delete()` has always had this; bulk `soft=True` (ADR-0017) now reaches it from a Core `UPDATE`.
2. `cache.written_models` called `session.info.pop(...)` unguarded, so a duck-typed session without `.info` raised `AttributeError` from every helper that invalidates (ADR-0012). The consumer's two failing tests were hand-rolled session doubles.
3. `bulk_upsert_mappings` takes its `INSERT` columns and `SET` clause from the first mapping (ADR-0016). A later mapping with an extra key had that value silently dropped (probe: `value=5` stored as `NULL`), and one missing a key failed with SQLAlchemy's `CompileError` (the multi-row `VALUES` needs every key).

## Decision
- Add `sqlmodel_crud_utils.mixins.UTCDateTime`, a `TypeDecorator` over `DateTime` that converts aware values to naive UTC on bind and leaves naive values and reads untouched. The three mixin columns use it. In-memory values stay timezone-aware.
- `written_models` treats a session without `.info` as having recorded nothing and returns just the models it was given.
- Add `validate_upsert_payload`: every mapping must have the same key set as the first, otherwise `ValueError` naming the row and keys, raised before any statement is sent. Key order is irrelevant.

## Consequences
- No schema change and no migration: the column type is still `TIMESTAMP WITHOUT TIME ZONE`, and Alembic compares `UTCDateTime` by its `DateTime` implementation. Existing rows keep their meaning (UTC wall-clock) because that is what correctly configured sessions already wrote.
- Rows written earlier under a non-UTC session `TimeZone` on psycopg3 are already shifted; this is not repaired here.
- `TimestampMixin` is unaffected: its `DateTime(timezone=True)` columns are server-filled.
- A payload that previously dropped an extra key now raises. This turns silent data loss into an error; payloads with differing keys never worked on a real database otherwise.
- Callers who want a tz-aware column should declare `DateTime(timezone=True)` on their own model; that is a schema change and stays their decision.

## Alternatives considered
- `DateTime(timezone=True)` on the mixins: correct semantics but a `TIMESTAMP` to `TIMESTAMPTZ` migration for every consumer. Rejected for a patch release.
- Return naive `_utc_now()` from the mixins: removes the shift but changes the in-memory value consumers compare against aware datetimes.
- Pad missing keys with `None` in later mappings: would hide the caller's mistake.
