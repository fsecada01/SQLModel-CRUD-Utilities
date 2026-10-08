"""
Real-SQLite tests for the bulk write helpers that take an ID list
(``delete_rows_within_id_list`` and ``bulk_update_rows``, issue #12).
"""

import pytest
import pytest_asyncio
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import Session, SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from sqlmodel_crud_utils.a_sync import bulk_update_rows as a_bulk_update_rows
from sqlmodel_crud_utils.a_sync import (
    delete_rows_within_id_list as a_delete_rows_within_id_list,
)
from sqlmodel_crud_utils.sync import (
    bulk_update_rows,
    delete_rows_within_id_list,
)

from .models import MockModel

SEED = [
    {"id": 1, "name": "one", "value": 10},
    {"id": 2, "name": "two", "value": 20},
    {"id": 3, "name": "three", "value": 30},
    {"id": 4, "name": "four", "value": 40},
]


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'bulk.sqlite'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as sess:
        sess.add_all([MockModel(**r) for r in SEED])
        sess.commit()
        yield sess
    engine.dispose()


@pytest_asyncio.fixture
async def a_session(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'bulk_async.sqlite'}"
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    async with AsyncSession(engine, expire_on_commit=False) as sess:
        sess.add_all([MockModel(**r) for r in SEED])
        await sess.commit()
        yield sess
    await engine.dispose()


def _stmt():
    return select(MockModel.id, MockModel.name, MockModel.value).order_by(
        MockModel.id
    )


def _rows(session):
    return [tuple(r) for r in session.execute(_stmt()).all()]


async def _a_rows(session):
    return [tuple(r) for r in (await session.execute(_stmt())).all()]


def test_delete_rows_removes_only_listed_ids(session):
    ok, count = delete_rows_within_id_list([1, 3], session, MockModel)
    assert (ok, count) == (True, 2)
    assert [r[0] for r in _rows(session)] == [2, 4]


def test_delete_rows_ignores_missing_ids(session):
    ok, count = delete_rows_within_id_list([2, 99], session, MockModel)
    assert (ok, count) == (True, 1)


def test_delete_rows_no_match_reports_false(session):
    result = delete_rows_within_id_list([98, 99], session, MockModel)
    assert result == (False, 0)
    assert len(_rows(session)) == 4


def test_delete_rows_empty_list_is_noop(session):
    assert delete_rows_within_id_list([], session, MockModel) == (False, 0)
    assert len(_rows(session)) == 4


def test_delete_rows_custom_pk_field(session):
    ok, count = delete_rows_within_id_list(
        ["one", "four"], session, MockModel, pk_field="name"
    )
    assert (ok, count) == (True, 2)


def test_delete_rows_bad_field_returns_false(session):
    result = delete_rows_within_id_list(
        [1], session, MockModel, pk_field="nope"
    )
    assert result == (False, 0)
    assert len(_rows(session)) == 4


def test_bulk_update_sets_values_on_listed_ids(session):
    ok, count = bulk_update_rows(
        [1, 2], {"value": 0, "name": "x"}, session, MockModel
    )
    assert (ok, count) == (True, 2)
    assert _rows(session) == [
        (1, "x", 0),
        (2, "x", 0),
        (3, "three", 30),
        (4, "four", 40),
    ]


def test_bulk_update_ignores_missing_ids(session):
    result = bulk_update_rows([4, 99], {"value": 1}, session, MockModel)
    assert result == (True, 1)


def test_bulk_update_no_match_and_empty_inputs(session):
    assert bulk_update_rows([99], {"value": 1}, session, MockModel) == (
        False,
        0,
    )
    assert bulk_update_rows([], {"value": 1}, session, MockModel) == (False, 0)
    assert bulk_update_rows([1], {}, session, MockModel) == (False, 0)


def test_bulk_update_bad_column_rolls_back(session):
    result = bulk_update_rows([1], {"nope": 1}, session, MockModel)
    assert result == (False, 0)
    assert _rows(session)[0] == (1, "one", 10)


@pytest.mark.asyncio
async def test_a_delete_rows_removes_only_listed_ids(a_session):
    ok, count = await a_delete_rows_within_id_list(
        [1, 3, 99], a_session, MockModel
    )
    assert (ok, count) == (True, 2)
    assert [r[0] for r in await _a_rows(a_session)] == [2, 4]


@pytest.mark.asyncio
async def test_a_delete_rows_empty_and_no_match(a_session):
    empty = await a_delete_rows_within_id_list([], a_session, MockModel)
    missing = await a_delete_rows_within_id_list([99], a_session, MockModel)
    assert empty == (False, 0)
    assert missing == (False, 0)


@pytest.mark.asyncio
async def test_a_delete_rows_bad_field_returns_false(a_session):
    result = await a_delete_rows_within_id_list(
        [1], a_session, MockModel, pk_field="nope"
    )
    assert result == (False, 0)
    assert len(await _a_rows(a_session)) == 4


@pytest.mark.asyncio
async def test_a_bulk_update_sets_values(a_session):
    ok, count = await a_bulk_update_rows(
        [2, 3, 99], {"value": 7}, a_session, MockModel
    )
    assert (ok, count) == (True, 2)
    assert [r[2] for r in await _a_rows(a_session)] == [10, 7, 7, 40]


@pytest.mark.asyncio
async def test_a_bulk_update_empty_and_bad_column(a_session):
    empty = await a_bulk_update_rows([], {"value": 1}, a_session, MockModel)
    bad = await a_bulk_update_rows([1], {"nope": 1}, a_session, MockModel)
    assert empty == (False, 0)
    assert bad == (False, 0)
    assert (await _a_rows(a_session))[0] == (1, "one", 10)
