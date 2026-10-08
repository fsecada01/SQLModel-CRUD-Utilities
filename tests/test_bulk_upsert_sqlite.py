"""
Real-SQLite regression tests for ``bulk_upsert_mappings`` (issue #13).

The mocked tests in ``test_sync_utils``/``test_async_utils`` cannot observe
statement ordering, so these run against an actual SQLite file.
"""

import pytest
import pytest_asyncio
from sqlalchemy import create_engine, event, select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import Session, SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from sqlmodel_crud_utils.a_sync import (
    bulk_upsert_mappings as async_bulk_upsert_mappings,
)
from sqlmodel_crud_utils.sync import bulk_upsert_mappings

from .models import MockModel

INITIAL = [
    {"id": 1, "name": "first", "value": 10},
    {"id": 2, "name": "second", "value": 20},
]
CONFLICTING = [
    {"id": 1, "name": "first-updated", "value": 11},
    {"id": 3, "name": "third", "value": 30},
]


def _as_tuples(rows):
    return {(r.id, r.name, r.value) for r in rows}


def _count_upserts(engine, counter: list):
    @event.listens_for(engine, "before_cursor_execute")
    def _count(conn, cursor, statement, *args):
        if statement.lstrip().upper().startswith("INSERT"):
            counter.append(statement)


@pytest.fixture
def sqlite_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'upsert.sqlite'}")
    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest_asyncio.fixture
async def aiosqlite_engine(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'upsert_async.sqlite'}"
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield engine
    await engine.dispose()


def test_sync_insert_returns_rows_and_persists(sqlite_engine):
    with Session(sqlite_engine) as session:
        success, rows = bulk_upsert_mappings(INITIAL, session, MockModel)
        returned = _as_tuples(rows)

    assert success is True
    assert returned == {(1, "first", 10), (2, "second", 20)}
    with Session(sqlite_engine) as session:
        persisted = session.exec(select(MockModel)).scalars().all()
    assert len(persisted) == 2


def test_sync_conflicting_upsert_updates_and_inserts(sqlite_engine):
    with Session(sqlite_engine) as session:
        bulk_upsert_mappings(INITIAL, session, MockModel)
        success, rows = bulk_upsert_mappings(CONFLICTING, session, MockModel)
        returned = _as_tuples(rows)

    assert success is True
    assert returned == {(1, "first-updated", 11), (3, "third", 30)}
    with Session(sqlite_engine) as session:
        persisted = {
            r.id: (r.name, r.value)
            for r in session.exec(select(MockModel)).scalars().all()
        }
    assert persisted == {
        1: ("first-updated", 11),
        2: ("second", 20),
        3: ("third", 30),
    }


def test_sync_upsert_statement_runs_once(sqlite_engine):
    statements: list = []
    _count_upserts(sqlite_engine, statements)

    with Session(sqlite_engine) as session:
        bulk_upsert_mappings(INITIAL, session, MockModel)

    assert len(statements) == 1


@pytest.mark.asyncio
async def test_async_insert_returns_rows_and_persists(aiosqlite_engine):
    async with AsyncSession(
        aiosqlite_engine, expire_on_commit=False
    ) as session:
        success, rows = await async_bulk_upsert_mappings(
            INITIAL, session, MockModel
        )
        returned = _as_tuples(rows)

    assert success is True
    assert returned == {(1, "first", 10), (2, "second", 20)}
    async with AsyncSession(
        aiosqlite_engine, expire_on_commit=False
    ) as session:
        persisted = (await session.exec(select(MockModel))).scalars().all()
    assert len(persisted) == 2


@pytest.mark.asyncio
async def test_async_conflicting_upsert_updates_and_inserts(aiosqlite_engine):
    async with AsyncSession(
        aiosqlite_engine, expire_on_commit=False
    ) as session:
        await async_bulk_upsert_mappings(INITIAL, session, MockModel)
        success, rows = await async_bulk_upsert_mappings(
            CONFLICTING, session, MockModel
        )
        returned = _as_tuples(rows)

    assert success is True
    assert returned == {(1, "first-updated", 11), (3, "third", 30)}
    async with AsyncSession(
        aiosqlite_engine, expire_on_commit=False
    ) as session:
        persisted = {
            r.id: (r.name, r.value)
            for r in (await session.exec(select(MockModel))).scalars().all()
        }
    assert persisted == {
        1: ("first-updated", 11),
        2: ("second", 20),
        3: ("third", 30),
    }


@pytest.mark.asyncio
async def test_async_upsert_statement_runs_once(aiosqlite_engine):
    statements: list = []
    _count_upserts(aiosqlite_engine.sync_engine, statements)

    async with AsyncSession(
        aiosqlite_engine, expire_on_commit=False
    ) as session:
        await async_bulk_upsert_mappings(INITIAL, session, MockModel)

    assert len(statements) == 1
