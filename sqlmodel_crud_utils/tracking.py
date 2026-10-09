"""Opt-in change tracking backed by a separate history table.

See ADR-0011. Models opt in by inheriting :class:`TrackChangesMixin`, and
tracking is switched on once per process with
:func:`register_change_tracking`. One record per inserted, updated or deleted
row is written, in the same transaction as the change, to the
``change_history`` table.

Only changes flushed through the ORM unit of work are recorded. The bulk
helpers (``bulk_upsert_mappings``, ``bulk_update_rows``,
``delete_rows_within_id_list``), raw SQL and ``session.execute(update(...))``
bypass ORM events and are never tracked.

The table lives on :data:`HISTORY_METADATA`, not ``SQLModel.metadata``, so it
is only created when you ask for it::

    HISTORY_METADATA.create_all(engine)
"""

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    event,
    inspect,
)
from sqlalchemy.orm import Session

HISTORY_METADATA = MetaData()

change_history_table = Table(
    "change_history",
    HISTORY_METADATA,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("table_name", String(255), nullable=False, index=True),
    Column("row_pk", String(255), nullable=False, index=True),
    Column("operation", String(16), nullable=False),
    Column("changes", JSON, nullable=False),
    Column("changed_at", DateTime(timezone=True), nullable=False),
    Column("changed_by", String(100), nullable=True),
)


class TrackChangesMixin:
    """Marker mixin: row changes to this model are recorded.

    It adds no columns. List column names in ``__track_exclude__`` to keep
    them out of the history (for example credentials).

    Example:
        >>> class Widget(TrackChangesMixin, SQLModel, table=True):
        ...     __track_exclude__ = ("token",)
        ...     id: Optional[int] = Field(default=None, primary_key=True)
        ...     name: str
        ...     token: Optional[str] = None
    """

    __track_exclude__: tuple[str, ...] = ()


def _jsonable(value: Any) -> Any:
    """Round-trip ``value`` through JSON, stringifying unknown types."""
    return json.loads(json.dumps(value, default=str))


def _row_pk(mapper, obj) -> str:
    return ",".join(str(v) for v in mapper.primary_key_from_instance(obj))


def _changes(obj, operation: str) -> dict[str, list]:
    """Build the ``{column: [old, new]}`` map for one flushed instance."""
    state = inspect(obj)
    excluded = set(getattr(obj, "__track_exclude__", ()))
    changes: dict[str, list] = {}
    for attr in state.mapper.column_attrs:
        if attr.key in excluded:
            continue
        hist = state.attrs[attr.key].history
        if operation == "insert":
            pair = [None, (hist.added or hist.unchanged or [None])[0]]
        elif operation == "delete":
            old = hist.deleted[0] if hist.deleted else None
            if old is None and hist.unchanged:
                old = hist.unchanged[0]
            pair = [old, None]
        else:
            if not hist.added:
                continue
            old = hist.deleted[0] if hist.deleted else None
            if old == hist.added[0]:
                continue
            pair = [old, hist.added[0]]
        changes[attr.key] = [_jsonable(v) for v in pair]
    return changes


def _record_flush(session: Session, flush_context) -> None:
    """``after_flush`` listener writing history rows on the flush connection."""
    batches = (
        ("insert", list(session.new)),
        ("update", list(session.dirty)),
        ("delete", list(session.deleted)),
    )
    rows = []
    now = datetime.now(timezone.utc)
    actor = session.info.get("changed_by")
    for operation, instances in batches:
        for obj in instances:
            if not isinstance(obj, TrackChangesMixin):
                continue
            changes = _changes(obj, operation)
            if operation == "update" and not changes:
                continue
            mapper = inspect(obj).mapper
            rows.append(
                {
                    "table_name": mapper.local_table.name,
                    "row_pk": _row_pk(mapper, obj),
                    "operation": operation,
                    "changes": changes,
                    "changed_at": now,
                    "changed_by": actor,
                }
            )
    if rows:
        session.connection().execute(change_history_table.insert(), rows)


def register_change_tracking() -> None:
    """Enable change tracking process-wide. Safe to call more than once.

    Installs one ``after_flush`` listener on :class:`sqlalchemy.orm.Session`.
    ``AsyncSession`` delegates to a sync ``Session``, so this covers both.
    Set ``session.info["changed_by"]`` (for ``AsyncSession`` use
    ``session.sync_session.info``) to stamp records with an actor.
    """
    if not event.contains(Session, "after_flush", _record_flush):
        event.listen(Session, "after_flush", _record_flush)
