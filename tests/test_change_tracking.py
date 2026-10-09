"""Tests for opt-in change tracking (ADR-0011)."""

from typing import Optional

import pytest
import pytest_asyncio
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import Field, Session, SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from sqlmodel_crud_utils import (
    HISTORY_METADATA,
    TrackChangesMixin,
    a_bulk_update_rows,
    a_delete_row,
    a_get_change_history,
    a_update_row,
    a_write_row,
    bulk_update_rows,
    delete_row,
    get_change_history,
    register_change_tracking,
    update_row,
    write_row,
)
from sqlmodel_crud_utils.tracking import change_history_table

from .models import MockModel


class TrackedThing(TrackChangesMixin, SQLModel, table=True):
    __tablename__ = "tracked_thing"
    __track_exclude__ = ("secret",)

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    qty: Optional[int] = None
    secret: Optional[str] = None


@pytest.fixture(autouse=True)
def _tracking_registered():
    register_change_tracking()
    register_change_tracking()  # idempotent


@pytest.fixture
def sess(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'track.sqlite'}")
    SQLModel.metadata.create_all(engine)
    HISTORY_METADATA.create_all(engine)
    with Session(engine, expire_on_commit=False) as s:
        yield s
    engine.dispose()


@pytest_asyncio.fixture
async def asess(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'track_a.sqlite'}"
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
        await conn.run_sync(HISTORY_METADATA.create_all)
    async with AsyncSession(engine, expire_on_commit=False) as s:
        yield s
    await engine.dispose()


def test_insert_update_delete_recorded(sess):
    sess.info["changed_by"] = "alice"
    ok, row = write_row(TrackedThing(name="a", qty=1, secret="x"), sess)
    assert ok
    update_row(row.id, {"qty": 2, "secret": "y"}, sess, TrackedThing)
    assert delete_row(row.id, sess, TrackedThing)

    ok, hist = get_change_history(sess, TrackedThing, row.id)
    assert ok
    assert [h["operation"] for h in hist] == ["insert", "update", "delete"]
    assert hist[0]["changes"]["name"] == [None, "a"]
    assert hist[1]["changes"] == {"qty": [1, 2]}
    assert hist[2]["changes"]["name"] == ["a", None]
    assert all(h["changed_by"] == "alice" for h in hist)
    assert all("secret" not in h["changes"] for h in hist)
    assert all(h["table_name"] == "tracked_thing" for h in hist)


def test_noop_update_not_recorded(sess):
    _, row = write_row(TrackedThing(name="a"), sess)
    update_row(row.id, {"name": "a"}, sess, TrackedThing)
    _, hist = get_change_history(sess, TrackedThing, row.id)
    assert [h["operation"] for h in hist] == ["insert"]


def test_untracked_models_ignored(sess):
    write_row(MockModel(name="m"), sess)
    assert sess.execute(select(change_history_table)).all() == []


def test_bulk_helpers_not_tracked(sess):
    _, row = write_row(TrackedThing(name="a", qty=1), sess)
    bulk_update_rows([row.id], {"qty": 9}, sess, TrackedThing)
    _, hist = get_change_history(sess, TrackedThing, row.id)
    assert [h["operation"] for h in hist] == ["insert"]


def test_history_rolls_back_with_change(sess):
    sess.add(TrackedThing(name="a"))
    sess.flush()
    sess.rollback()
    assert sess.execute(select(change_history_table)).all() == []


@pytest.mark.asyncio
async def test_async_parity(asess):
    asess.sync_session.info["changed_by"] = "bob"
    ok, row = await a_write_row(TrackedThing(name="a", qty=1), asess)
    assert ok
    await a_update_row(row.id, {"qty": 5}, asess, TrackedThing)
    await a_bulk_update_rows([row.id], {"qty": 7}, asess, TrackedThing)
    assert await a_delete_row(row.id, asess, TrackedThing)
    ok, hist = await a_get_change_history(asess, TrackedThing, row.id)
    assert ok
    assert [h["operation"] for h in hist] == ["insert", "update", "delete"]
    assert hist[1]["changes"] == {"qty": [1, 5]}
    assert hist[0]["changed_by"] == "bob"
