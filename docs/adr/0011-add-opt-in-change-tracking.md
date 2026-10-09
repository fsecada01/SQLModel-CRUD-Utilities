# 0011. Add opt-in change tracking in a separate history table

- Status: accepted
- Date: 2026-10-09

## Context
ADR-0007 deferred change tracking as complex. Two questions had to be settled before building it: how it relates to `AuditMixin` / `TimestampMixin`, and what it can observe, since the bulk helpers (`bulk_upsert_mappings`, `bulk_update_rows`, `delete_rows_within_id_list`) use Core statements and bypass ORM events (ADR-0004, ADR-0005).

## Decision
This supersedes ADR-0007 for change tracking only. Build it, opt-in, as a separate history table rather than extending the audit mixins.

- `AuditMixin` / `TimestampMixin` answer "when was this row last touched and by whom" with columns on the row itself. They keep no old values and cannot show history. They are unchanged; change tracking complements them and does not depend on them.
- A model opts in by inheriting `TrackChangesMixin` (a plain marker class with no columns, so no schema change to tracked tables). `__track_exclude__` lists columns to leave out of the record (for example secrets).
- `register_change_tracking()` installs one SQLAlchemy `after_flush` listener on `sqlalchemy.orm.Session`. `AsyncSession` wraps a sync `Session`, so one listener covers both. Nothing is recorded until it is called.
- Records go into a `change_history` table defined on its own `MetaData` (`HISTORY_METADATA`), not `SQLModel.metadata`, so importing the library never adds a table to a user's `create_all` or Alembic autogenerate. Users create it explicitly with `HISTORY_METADATA.create_all(engine)`. Each record holds table name, primary key (as text), operation (`insert`/`update`/`delete`), a JSON map of column to `[old, new]`, `changed_at`, and `changed_by` taken from `session.info["changed_by"]` when set. Rows are written with Core inserts on the session's own connection, so the history commits or rolls back with the change it describes.
- `get_change_history(session, model, pk_value)` and `a_get_change_history` read the history, newest last, returning the usual `(success, data)` tuple. No new runtime dependency.

### What is tracked
Changes made through the ORM unit of work to instances of opted-in models: `write_row`, `insert_data_rows`, `update_row`, `delete_row`, `get_one_or_create`, and any direct `session.add` / attribute assignment / `session.delete` followed by flush or commit. Updates that leave every tracked column unchanged record nothing.

### What is not tracked
- The bulk helpers `bulk_upsert_mappings`, `bulk_update_rows` and `delete_rows_within_id_list`. They issue Core statements, so no ORM flush events fire. They are deliberately not made to write history: doing so would need per-row old values (an extra read per chunk) and would defeat their purpose. Callers who need history for bulk changes must use the ORM helpers.
- Raw SQL, `session.execute(update(...))`, other processes, and database-side triggers or cascades that do not go through the ORM.
- Models that do not inherit `TrackChangesMixin`.

## Consequences
- Phase #25 (caching) must not assume change tracking is a complete change feed: bulk helpers produce no history rows and no ORM events, so cache invalidation has to be done explicitly by those helpers rather than by listening to tracking.
- The history table grows without bound; pruning is the user's responsibility.
- Old values come from SQLAlchemy attribute history, so they are only accurate for attributes loaded before modification.
- Revisit if users need bulk-helper history; that would be a new ADR and an opt-in parameter.

## Alternatives considered
- Extend `AuditMixin` with old-value columns: cannot hold per-column history and would change tracked tables.
- Database triggers: dialect specific, outside the library's scope.
- Put the history table in `SQLModel.metadata`: simpler reads, but silently adds a table for every user.
