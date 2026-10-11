"""
How the ID-list bulk helpers interact with the mixins (issue #51, ADR-0017).

Every test runs against both the sync and async API on real SQLite through a
small adapter, so the two modules cannot drift apart on these semantics.

Pinned behaviour:

* ``delete_rows_within_id_list`` is a hard DELETE unless ``soft=True``.
* ``soft=True`` marks rows exactly as ``SoftDeleteMixin.soft_delete`` does.
* ``bulk_update_rows`` refreshes ``updated_at`` through the column's
  ``onupdate`` for both ``TimestampMixin`` and ``AuditMixin`` but never sets
  ``updated_by``.
"""

import inspect
from datetime import datetime, timedelta, timezone
from typing import Optional

import pytest
import pytest_asyncio
from sqlalchemy import CheckConstraint, create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import Field, Session, SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

import sqlmodel_crud_utils as scu
from sqlmodel_crud_utils import a_sync, sync
from sqlmodel_crud_utils.cache import InMemoryCache, configure_cache
from sqlmodel_crud_utils.mixins import (
    AuditMixin,
    SoftDeleteMixin,
    TimestampMixin,
)


class SoftItem(SQLModel, SoftDeleteMixin, table=True):
    __tablename__ = "bulk51_soft_item"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str


class SoftSku(SQLModel, SoftDeleteMixin, table=True):
    __tablename__ = "bulk51_soft_sku"

    sku: str = Field(primary_key=True)
    name: str


class SoftPair(SQLModel, SoftDeleteMixin, table=True):
    __tablename__ = "bulk51_soft_pair"

    tenant: str = Field(primary_key=True)
    code: str = Field(primary_key=True)


class AuditSoft(SQLModel, AuditMixin, SoftDeleteMixin, table=True):
    __tablename__ = "bulk51_audit_soft"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str


class AuditOnly(SQLModel, AuditMixin, table=True):
    __tablename__ = "bulk51_audit_only"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str


class StampOnly(TimestampMixin, SQLModel, table=True):
    __tablename__ = "bulk51_stamp_only"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str


class PartialSoft(SQLModel, table=True):
    """Has ``is_deleted`` but neither ``deleted_at`` nor ``deleted_by``."""

    __tablename__ = "bulk51_partial_soft"

    id: Optional[int] = Field(default=None, primary_key=True)
    is_deleted: bool = Field(default=False)


class Plain(SQLModel, table=True):
    __tablename__ = "bulk51_plain"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str


class GuardedSoft(SQLModel, SoftDeleteMixin, table=True):
    """Soft-deleting id 3 violates a CHECK, so that UPDATE fails."""

    __tablename__ = "bulk51_guarded_soft"
    __table_args__ = (CheckConstraint("NOT (is_deleted AND id = 3)"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str


def _naive_utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Env:
    """One interface over the sync and async sessions."""

    def __init__(self, kind, session, engine):
        self.kind = kind
        self.session = session
        self.engine = engine

    async def add(self, *objs):
        self.session.add_all(objs)
        if self.kind == "sync":
            self.session.commit()
        else:
            await self.session.commit()

    async def delete(self, ids, model, **kw):
        if self.kind == "sync":
            return sync.delete_rows_within_id_list(
                ids, self.session, model, **kw
            )
        return await a_sync.delete_rows_within_id_list(
            ids, self.session, model, **kw
        )

    async def update(self, ids, data, model, **kw):
        if self.kind == "sync":
            return sync.bulk_update_rows(ids, data, self.session, model, **kw)
        return await a_sync.bulk_update_rows(
            ids, data, self.session, model, **kw
        )

    async def get_rows(self, model, **kw):
        if self.kind == "sync":
            return sync.get_rows(self.session, model, **kw)
        return await a_sync.get_rows(self.session, model, **kw)

    async def get_row(self, id_, model, **kw):
        if self.kind == "sync":
            return sync.get_row(id_, self.session, model, **kw)
        return await a_sync.get_row(id_, self.session, model, **kw)

    async def table(self, model):
        """Rows as dicts straight from the table, keyed by primary key."""
        table = model.__table__
        stmnt = select(*table.columns)
        if self.kind == "sync":
            result = self.session.exec(stmnt)
        else:
            result = await self.session.exec(stmnt)
        pk = [c.key for c in table.primary_key.columns]
        out = {}
        for row in result.all():
            mapping = dict(row._mapping)
            key = tuple(mapping[k] for k in pk)
            out[key[0] if len(key) == 1 else key] = mapping
        return out

    def record(self, verb):
        seen = []

        @event.listens_for(self.engine, "before_cursor_execute")
        def _on_execute(conn, cursor, statement, parameters, *args):
            if statement.lstrip().upper().startswith(verb):
                seen.append(statement)

        return seen


@pytest_asyncio.fixture(params=["sync", "async"])
async def env(request, tmp_path):
    if request.param == "sync":
        engine = create_engine(f"sqlite:///{tmp_path / 'm.sqlite'}")
        SQLModel.metadata.create_all(engine)
        with Session(engine, expire_on_commit=False) as sess:
            yield Env("sync", sess, engine)
        engine.dispose()
    else:
        engine = create_async_engine(
            f"sqlite+aiosqlite:///{tmp_path / 'ma.sqlite'}"
        )
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        async with AsyncSession(engine, expire_on_commit=False) as sess:
            yield Env("async", sess, engine.sync_engine)
        await engine.dispose()


@pytest.fixture
def cache():
    backend = InMemoryCache(default_ttl=60)
    configure_cache(backend)
    yield backend
    configure_cache(None)


async def _seed_items(env, model=SoftItem, n=5):
    await env.add(*[model(id=i, name=f"n{i}") for i in range(1, n + 1)])


# --- hard delete is unchanged ----------------------------------------------


@pytest.mark.asyncio
async def test_hard_delete_is_the_default_on_soft_delete_models(env):
    await _seed_items(env)
    ok, count = await env.delete([1, 2], SoftItem)
    assert (ok, count) == (True, 2)
    assert sorted(await env.table(SoftItem)) == [3, 4, 5]


@pytest.mark.asyncio
async def test_explicit_soft_false_is_the_same_hard_delete(env):
    await _seed_items(env)
    ok, count = await env.delete([1], SoftItem, soft=False)
    assert (ok, count) == (True, 1)
    assert 1 not in await env.table(SoftItem)


# --- soft delete ------------------------------------------------------------


@pytest.mark.asyncio
async def test_soft_delete_marks_rows_and_keeps_them(env):
    await _seed_items(env)
    before = _naive_utc_now()
    ok, count = await env.delete([1, 3], SoftItem, soft=True)
    after = _naive_utc_now()
    assert (ok, count) == (True, 2)

    rows = await env.table(SoftItem)
    assert sorted(rows) == [1, 2, 3, 4, 5]
    for pk in (1, 3):
        assert rows[pk]["is_deleted"] is True
        assert before - timedelta(seconds=1) <= rows[pk]["deleted_at"]
        assert rows[pk]["deleted_at"] <= after + timedelta(seconds=1)
        assert rows[pk]["deleted_by"] is None
        assert rows[pk]["name"] == f"n{pk}"
    for pk in (2, 4, 5):
        assert rows[pk]["is_deleted"] is False
        assert rows[pk]["deleted_at"] is None


@pytest.mark.asyncio
async def test_soft_delete_records_deleted_by(env):
    await _seed_items(env)
    await env.delete([2], SoftItem, soft=True, deleted_by="admin")
    rows = await env.table(SoftItem)
    assert rows[2]["deleted_by"] == "admin"
    assert rows[1]["deleted_by"] is None


@pytest.mark.asyncio
async def test_soft_delete_matches_the_mixin_method(env):
    """The bulk write leaves the same state ``soft_delete`` would."""
    await _seed_items(env, n=2)
    via_mixin = SoftItem(id=99, name="m")
    via_mixin.soft_delete(user="bob")

    await env.delete([1], SoftItem, soft=True, deleted_by="bob")
    row = (await env.table(SoftItem))[1]
    assert row["is_deleted"] is via_mixin.is_deleted is True
    assert row["deleted_by"] == via_mixin.deleted_by == "bob"
    assert row["deleted_at"] is not None and via_mixin.deleted_at is not None


@pytest.mark.asyncio
async def test_soft_delete_leaves_already_deleted_rows_untouched(env):
    await _seed_items(env, n=3)
    await env.delete([1], SoftItem, soft=True, deleted_by="first")
    first = (await env.table(SoftItem))[1]

    ok, count = await env.delete(
        [1, 2], SoftItem, soft=True, deleted_by="second"
    )
    # Only row 2 changed; row 1 was already deleted and is not counted.
    assert (ok, count) == (True, 1)
    rows = await env.table(SoftItem)
    assert rows[1]["deleted_at"] == first["deleted_at"]
    assert rows[1]["deleted_by"] == "first"
    assert rows[2]["deleted_by"] == "second"


@pytest.mark.asyncio
async def test_soft_delete_twice_counts_zero_the_second_time(env):
    await _seed_items(env, n=2)
    assert await env.delete([1, 2], SoftItem, soft=True) == (True, 2)
    assert await env.delete([1, 2], SoftItem, soft=True) == (True, 0)


@pytest.mark.asyncio
async def test_soft_delete_ignores_missing_and_empty_ids(env):
    await _seed_items(env, n=2)
    assert await env.delete([2, 98, 99], SoftItem, soft=True) == (True, 1)
    updates = env.record("UPDATE")
    assert await env.delete([], SoftItem, soft=True) == (True, 0)
    assert updates == []
    rows = await env.table(SoftItem)
    assert sorted(rows) == [1, 2]
    assert rows[1]["is_deleted"] is False


@pytest.mark.asyncio
async def test_soft_delete_counts_rows_not_duplicate_ids(env):
    await _seed_items(env, n=3)
    ok, count = await env.delete([1, 1, 2, 2, 2], SoftItem, soft=True)
    assert (ok, count) == (True, 2)


@pytest.mark.asyncio
async def test_soft_delete_chunks_into_one_statement_per_batch(env):
    await _seed_items(env, n=5)
    updates = env.record("UPDATE")
    deletes = env.record("DELETE")
    ok, count = await env.delete(
        [1, 2, 3, 4, 5, 99], SoftItem, soft=True, chunk_size=2
    )
    assert (ok, count) == (True, 5)
    assert len(updates) == 3
    assert deletes == []
    rows = await env.table(SoftItem)
    assert all(r["is_deleted"] for r in rows.values())
    # One timestamp for the whole call, whatever the chunking.
    assert len({r["deleted_at"] for r in rows.values()}) == 1


@pytest.mark.asyncio
async def test_soft_delete_rolls_back_every_chunk_on_error(env):
    await env.add(*[GuardedSoft(id=i, name=f"g{i}") for i in range(1, 5)])
    with pytest.raises(IntegrityError):
        await env.delete([1, 2, 3, 4], GuardedSoft, soft=True, chunk_size=2)
    rows = await env.table(GuardedSoft)
    assert [r["is_deleted"] for r in rows.values()] == [False] * 4
    assert [r["deleted_at"] for r in rows.values()] == [None] * 4


@pytest.mark.asyncio
async def test_soft_delete_uses_the_given_primary_key_field(env):
    await env.add(
        SoftSku(sku="a", name="A"),
        SoftSku(sku="b", name="B"),
        SoftSku(sku="c", name="C"),
    )
    ok, count = await env.delete(
        ["a", "c", "zzz"], SoftSku, pk_field="sku", soft=True, deleted_by="u"
    )
    assert (ok, count) == (True, 2)
    rows = await env.table(SoftSku)
    assert {k: r["is_deleted"] for k, r in rows.items()} == {
        "a": True,
        "b": False,
        "c": True,
    }


@pytest.mark.asyncio
async def test_soft_delete_composite_key_matches_the_named_column(env):
    await env.add(
        SoftPair(tenant="t1", code="x"),
        SoftPair(tenant="t2", code="x"),
        SoftPair(tenant="t1", code="y"),
    )
    ok, count = await env.delete(["x"], SoftPair, pk_field="code", soft=True)
    # pk_field names one column, as in the hard delete: every row with that
    # value is matched.
    assert (ok, count) == (True, 2)
    rows = await env.table(SoftPair)
    assert rows[("t1", "y")]["is_deleted"] is False
    assert rows[("t1", "x")]["is_deleted"] is True
    assert rows[("t2", "x")]["is_deleted"] is True


@pytest.mark.asyncio
async def test_soft_delete_with_audit_mixin_refreshes_updated_at_only(env):
    await env.add(AuditSoft(id=1, name="a"), AuditSoft(id=2, name="b"))
    assert (await env.table(AuditSoft))[1]["updated_at"] is None
    before = _naive_utc_now()

    await env.delete([1], AuditSoft, soft=True, deleted_by="admin")

    rows = await env.table(AuditSoft)
    assert rows[1]["is_deleted"] is True
    assert rows[1]["deleted_by"] == "admin"
    assert rows[1]["updated_at"] is not None
    assert rows[1]["updated_at"] >= before - timedelta(seconds=1)
    assert rows[1]["updated_by"] is None
    assert rows[2]["updated_at"] is None


@pytest.mark.asyncio
async def test_soft_delete_synchronizes_loaded_instances(env):
    """The ORM-enabled UPDATE also updates objects already in the session."""
    await _seed_items(env, n=2)
    ok, row = await env.get_row(1, SoftItem)
    assert row.is_deleted is False
    await env.delete([1], SoftItem, soft=True, deleted_by="admin")
    assert row.is_deleted is True
    assert row.deleted_by == "admin"
    assert row.deleted_at is not None


@pytest.mark.asyncio
async def test_soft_delete_invalidates_the_model_cache(env, cache):
    await _seed_items(env, n=3)
    ok, rows = await env.get_rows(SoftItem, use_cache=True)
    assert [r.is_deleted for r in rows] == [False, False, False]
    # A second read is a cache hit and must still say "not deleted".
    ok, rows = await env.get_rows(SoftItem, use_cache=True)
    assert [r.is_deleted for r in rows] == [False, False, False]

    await env.delete([1, 2], SoftItem, soft=True)

    ok, rows = await env.get_rows(SoftItem, use_cache=True)
    assert sorted((r.id, r.is_deleted) for r in rows) == [
        (1, True),
        (2, True),
        (3, False),
    ]


@pytest.mark.asyncio
async def test_failed_soft_delete_does_not_invalidate_the_cache(env, cache):
    await env.add(*[GuardedSoft(id=i, name=f"g{i}") for i in range(1, 4)])
    await env.get_rows(GuardedSoft, use_cache=True)
    with pytest.raises(IntegrityError):
        await env.delete([1, 2, 3], GuardedSoft, soft=True, chunk_size=2)
    ok, rows = await env.get_rows(GuardedSoft, use_cache=True)
    assert [r.is_deleted for r in rows] == [False, False, False]


# --- validation -------------------------------------------------------------


@pytest.mark.asyncio
async def test_soft_delete_requires_the_mixin_columns(env):
    await env.add(Plain(id=1, name="p"))
    with pytest.raises(ValueError) as exc:
        await env.delete([1], Plain, soft=True)
    message = str(exc.value)
    for column in ("is_deleted", "deleted_at", "deleted_by"):
        assert column in message
    assert "Plain" in message
    assert 1 in await env.table(Plain)


@pytest.mark.asyncio
async def test_soft_delete_names_only_the_missing_columns(env):
    await env.add(PartialSoft(id=1))
    with pytest.raises(ValueError) as exc:
        await env.delete([1], PartialSoft, soft=True)
    message = str(exc.value)
    assert "deleted_at" in message
    assert "deleted_by" in message
    assert "is_deleted" not in message.split("missing")[-1]
    assert (await env.table(PartialSoft))[1]["is_deleted"] is False


@pytest.mark.asyncio
async def test_deleted_by_without_soft_is_rejected_and_deletes_nothing(env):
    await _seed_items(env, n=2)
    updates = env.record("UPDATE")
    deletes = env.record("DELETE")
    with pytest.raises(ValueError, match="deleted_by"):
        await env.delete([1], SoftItem, deleted_by="admin")
    with pytest.raises(ValueError, match="deleted_by"):
        await env.delete([1], SoftItem, soft=False, deleted_by="admin")
    assert updates == [] and deletes == []
    assert sorted(await env.table(SoftItem)) == [1, 2]


@pytest.mark.asyncio
async def test_soft_delete_rejects_non_primary_key_field(env):
    await _seed_items(env, n=2)
    with pytest.raises(ValueError):
        await env.delete([1], SoftItem, pk_field="name", soft=True)
    assert (await env.table(SoftItem))[1]["is_deleted"] is False


@pytest.mark.asyncio
async def test_soft_delete_rejects_non_positive_chunk_size(env):
    await _seed_items(env, n=2)
    with pytest.raises(ValueError):
        await env.delete([1], SoftItem, soft=True, chunk_size=0)
    assert (await env.table(SoftItem))[1]["is_deleted"] is False


# --- signatures -------------------------------------------------------------


def test_new_parameters_are_appended_and_identical_in_sync_and_async():
    shapes = []
    for func in (
        sync.delete_rows_within_id_list,
        a_sync.delete_rows_within_id_list,
    ):
        params = list(inspect.signature(func).parameters.values())
        shapes.append([(p.name, p.kind, p.default) for p in params])
    assert shapes[0] == shapes[1]
    names = [name for name, _, _ in shapes[0]]
    assert names == [
        "id_str_list",
        "session_inst",
        "model",
        "pk_field",
        "chunk_size",
        "soft",
        "deleted_by",
    ]
    defaults = {name: default for name, _, default in shapes[0]}
    assert defaults["soft"] is False
    assert defaults["deleted_by"] is None
    assert scu.delete_rows_within_id_list is sync.delete_rows_within_id_list


# --- bulk_update_rows and the mixins (pins the corrected docs) --------------


@pytest.mark.asyncio
async def test_bulk_update_refreshes_audit_updated_at_not_updated_by(env):
    await env.add(AuditOnly(id=1, name="a"), AuditOnly(id=2, name="b"))
    rows = await env.table(AuditOnly)
    assert rows[1]["updated_at"] is None
    assert rows[1]["updated_by"] is None
    before = _naive_utc_now()

    ok, count = await env.update([1], {"name": "renamed"}, AuditOnly)

    assert (ok, count) == (True, 1)
    rows = await env.table(AuditOnly)
    assert rows[1]["name"] == "renamed"
    assert rows[1]["updated_at"] is not None
    assert rows[1]["updated_at"] >= before - timedelta(seconds=1)
    assert rows[1]["updated_by"] is None
    # Rows outside the ID list keep their previous values.
    assert rows[2]["updated_at"] is None


@pytest.mark.asyncio
async def test_bulk_update_sets_updated_by_only_when_passed_in_data(env):
    await env.add(AuditOnly(id=1, name="a"))
    await env.update([1], {"name": "x", "updated_by": "carol"}, AuditOnly)
    rows = await env.table(AuditOnly)
    assert rows[1]["updated_by"] == "carol"
    assert rows[1]["updated_at"] is not None


@pytest.mark.asyncio
async def test_bulk_update_refreshes_timestamp_mixin_updated_at(env):
    await env.add(StampOnly(id=1, name="a"))
    created = (await env.table(StampOnly))[1]["updated_at"]
    await env.update([1], {"name": "b"}, StampOnly)
    row = (await env.table(StampOnly))[1]
    assert row["name"] == "b"
    assert row["updated_at"] is not None
    assert row["updated_at"] >= created


@pytest.mark.asyncio
async def test_bulk_update_does_not_touch_soft_delete_fields(env):
    await env.add(SoftItem(id=1, name="a"))
    await env.update([1], {"name": "b"}, SoftItem)
    row = (await env.table(SoftItem))[1]
    assert row["name"] == "b"
    assert row["is_deleted"] is False
    assert row["deleted_at"] is None
    assert row["deleted_by"] is None
