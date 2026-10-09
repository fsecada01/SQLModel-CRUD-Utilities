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
    and_,
    event,
    inspect,
    select,
)
from sqlalchemy.orm import Session

HISTORY_METADATA = MetaData()

change_history_table = Table(
    "change_history",
    HISTORY_METADATA,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("table_name", String(255), nullable=False, index=True),
    Column("table_schema", String(255), nullable=True),
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


_ACTOR_MAX_LENGTH = 100


def format_row_pk(value: Any) -> str:
    """Render a primary-key value the way history rows store it.

    A composite key is given as a tuple or list in column order and stored
    comma-joined.
    """
    if isinstance(value, (tuple, list)):
        return ",".join(str(v) for v in value)
    return str(value)


def history_select(model: Any, id_str: Any):
    """Build the SELECT returning one row's history, oldest first.

    Rows are matched on table name, schema and primary key, so same-named
    tables in different schemas keep separate histories.
    """
    table = model.__table__
    schema_filter = (
        change_history_table.c.table_schema.is_(None)
        if table.schema is None
        else change_history_table.c.table_schema == table.schema
    )
    return (
        select(change_history_table)
        .where(change_history_table.c.table_name == table.name)
        .where(schema_filter)
        .where(change_history_table.c.row_pk == format_row_pk(id_str))
        .order_by(change_history_table.c.id)
    )


def _row_pk(mapper, obj) -> str:
    return format_row_pk(mapper.primary_key_from_instance(obj))


def _changes(obj, operation: str) -> dict[str, list]:
    """Build the ``{column: [old, new]}`` map for one flushed instance."""
    state = inspect(obj)
    stored = state.info.get(_PRE_IMAGE_KEY, {})
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
            old = hist.deleted[0] if hist.deleted else stored.get(attr.key)
            if old == hist.added[0]:
                continue
            pair = [old, hist.added[0]]
        changes[attr.key] = [_jsonable(v) for v in pair]
    return changes


_PRE_IMAGE_KEY = "_change_tracking_pre_image"


def _capture_pre_images(session: Session, flush_context, instances) -> None:
    """``before_flush`` listener recovering old values lost to expiry.

    Assigning to an expired attribute leaves no previous value in the
    attribute history, so the stored value is read once before the flush.
    Only attributes changed without a recorded previous value are fetched,
    and nothing is queried when every old value is already loaded.
    """
    for obj in list(session.dirty):
        if not isinstance(obj, TrackChangesMixin):
            continue
        state = inspect(obj)
        excluded = set(getattr(obj, "__track_exclude__", ()))
        lost = [
            attr
            for attr in state.mapper.column_attrs
            if attr.key not in excluded
            and state.attrs[attr.key].history.added
            and not state.attrs[attr.key].history.deleted
        ]
        if not lost or state.identity is None:
            continue
        mapper = state.mapper
        where = and_(
            *(
                col == val
                for col, val in zip(mapper.primary_key, state.identity)
            )
        )
        columns = [attr.columns[0] for attr in lost]
        with session.no_autoflush:
            row = session.execute(select(*columns).where(where)).first()
        if row is not None:
            state.info[_PRE_IMAGE_KEY] = {
                attr.key: value for attr, value in zip(lost, row)
            }


def _record_flush(session: Session, flush_context) -> None:
    """``after_flush`` listener writing history rows on the flush connection."""
    batches = (
        ("insert", list(session.new)),
        ("update", list(session.dirty)),
        ("delete", list(session.deleted)),
    )
    pending: dict[int, tuple[Any, list[dict]]] = {}
    now = datetime.now(timezone.utc)
    actor = session.info.get("changed_by")
    if actor is not None:
        actor = str(actor)[:_ACTOR_MAX_LENGTH]
    for operation, instances in batches:
        for obj in instances:
            if not isinstance(obj, TrackChangesMixin):
                continue
            changes = _changes(obj, operation)
            if operation == "update" and not changes:
                continue
            mapper = inspect(obj).mapper
            bind = session.get_bind(mapper=mapper)
            pending.setdefault(id(bind), (mapper, []))[1].append(
                {
                    "table_name": mapper.local_table.name,
                    "table_schema": mapper.local_table.schema,
                    "row_pk": _row_pk(mapper, obj),
                    "operation": operation,
                    "changes": changes,
                    "changed_at": now,
                    "changed_by": actor,
                }
            )
            inspect(obj).info.pop(_PRE_IMAGE_KEY, None)
    for mapper, rows in pending.values():
        connection = session.connection(bind_arguments={"mapper": mapper})
        connection.execute(change_history_table.insert(), rows)


def register_change_tracking() -> None:
    """Enable change tracking process-wide. Safe to call more than once.

    Installs ``before_flush`` and ``after_flush`` listeners on
    :class:`sqlalchemy.orm.Session`.
    ``AsyncSession`` delegates to a sync ``Session``, so this covers both.
    Set ``session.info["changed_by"]`` (for ``AsyncSession`` use
    ``session.sync_session.info``) to stamp records with an actor.
    """
    if not event.contains(Session, "after_flush", _record_flush):
        event.listen(Session, "after_flush", _record_flush)
    if not event.contains(Session, "before_flush", _capture_pre_images):
        event.listen(Session, "before_flush", _capture_pre_images)
