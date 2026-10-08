"""
Real-SQLite regression tests for ``get_rows`` with a custom ``stmnt``
(issue #11). The mocked tests cannot observe the LIMIT/OFFSET applied to the
executed statement, so these run against an actual SQLite file.
"""

import pytest
import pytest_asyncio
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import Session, SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from sqlmodel_crud_utils.a_sync import get_rows as async_get_rows
from sqlmodel_crud_utils.sync import get_rows

from .models import MockModel

ROW_COUNT = 150


def _seed():
    return [
        MockModel(id=i, name=f"row-{i}", value=i)
        for i in range(1, ROW_COUNT + 1)
    ]


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'rows.sqlite'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as sess:
        sess.add_all(_seed())
        sess.commit()
        yield sess
    engine.dispose()


@pytest_asyncio.fixture
async def async_session(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'rows_async.sqlite'}"
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    async with AsyncSession(engine, expire_on_commit=False) as sess:
        sess.add_all(_seed())
        await sess.commit()
        yield sess
    await engine.dispose()


def test_sync_custom_stmnt_is_not_paginated(session):
    success, rows = get_rows(
        session_inst=session, model=MockModel, stmnt=select(MockModel.id)
    )

    assert success is True
    assert len(rows) == ROW_COUNT


def test_sync_default_path_still_paginates(session):
    _, first = get_rows(session_inst=session, model=MockModel)
    _, second = get_rows(session_inst=session, model=MockModel, page=2)

    assert len(first) == 100
    assert len(second) == ROW_COUNT - 100


def test_sync_default_path_honours_page_size(session):
    _, rows = get_rows(session_inst=session, model=MockModel, page_size=10)

    assert len(rows) == 10


def test_sync_custom_stmnt_ignores_page_size(session):
    _, rows = get_rows(
        session_inst=session,
        model=MockModel,
        stmnt=select(MockModel.id),
        page_size=10,
    )

    assert len(rows) == ROW_COUNT


def test_sync_custom_stmnt_caller_limit_is_respected(session):
    _, rows = get_rows(
        session_inst=session,
        model=MockModel,
        stmnt=select(MockModel.id).order_by(MockModel.id).limit(5),
    )

    assert rows == [1, 2, 3, 4, 5]


@pytest.mark.asyncio
async def test_async_custom_stmnt_is_not_paginated(async_session):
    success, rows = await async_get_rows(
        session_inst=async_session,
        model=MockModel,
        stmnt=select(MockModel.id),
    )

    assert success is True
    assert len(rows) == ROW_COUNT


@pytest.mark.asyncio
async def test_async_default_path_still_paginates(async_session):
    _, first = await async_get_rows(session_inst=async_session, model=MockModel)
    _, second = await async_get_rows(
        session_inst=async_session, model=MockModel, page=2
    )

    assert len(first) == 100
    assert len(second) == ROW_COUNT - 100


@pytest.mark.asyncio
async def test_async_custom_stmnt_ignores_page_size(async_session):
    _, rows = await async_get_rows(
        session_inst=async_session,
        model=MockModel,
        stmnt=select(MockModel.id),
        page_size=10,
    )

    assert len(rows) == ROW_COUNT
