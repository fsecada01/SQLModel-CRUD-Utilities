"""
Real-SQLite tests for the bulk write helpers that take an ID list
(``delete_rows_within_id_list`` and ``bulk_update_rows``, issue #12).
"""

from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
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


def test_delete_rows_no_match_succeeds_with_zero_count(session):
    result = delete_rows_within_id_list([98, 99], session, MockModel)
    assert result == (True, 0)
    assert len(_rows(session)) == 4


def test_delete_rows_empty_list_is_noop(session):
    assert delete_rows_within_id_list([], session, MockModel) == (True, 0)
    assert len(_rows(session)) == 4


@pytest.mark.parametrize("bad_field", ["name", "value", "nope"])
def test_delete_rows_rejects_non_primary_key_field(session, bad_field):
    with pytest.raises(ValueError):
        delete_rows_within_id_list([1], session, MockModel, pk_field=bad_field)
    assert len(_rows(session)) == 4


def test_delete_rows_chunks_large_id_lists(session):
    ok, count = delete_rows_within_id_list(
        [1, 2, 3, 4, 99], session, MockModel, chunk_size=2
    )
    assert (ok, count) == (True, 4)
    assert _rows(session) == []


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


def test_bulk_update_no_match_and_empty_ids(session):
    assert bulk_update_rows([99], {"value": 1}, session, MockModel) == (
        True,
        0,
    )
    assert bulk_update_rows([], {"value": 1}, session, MockModel) == (True, 0)


def test_bulk_update_empty_data_is_rejected(session):
    with pytest.raises(ValueError):
        bulk_update_rows([1], {}, session, MockModel)


@pytest.mark.parametrize("bad_data", [{"nope": 1}, {"id": 5}])
def test_bulk_update_rejects_unknown_and_primary_key_columns(session, bad_data):
    with pytest.raises(ValueError):
        bulk_update_rows([1], bad_data, session, MockModel)
    assert _rows(session)[0] == (1, "one", 10)


def test_bulk_update_rejects_non_primary_key_field(session):
    with pytest.raises(ValueError):
        bulk_update_rows([1], {"value": 1}, session, MockModel, pk_field="name")


def test_bulk_update_chunks_large_id_lists(session):
    ok, count = bulk_update_rows(
        [1, 2, 3, 4, 99], {"value": 5}, session, MockModel, chunk_size=2
    )
    assert (ok, count) == (True, 4)
    assert [r[2] for r in _rows(session)] == [5, 5, 5, 5]


def test_bulk_update_database_error_rolls_back_and_raises(session):
    with pytest.raises(IntegrityError):
        bulk_update_rows([1, 2], {"name": None}, session, MockModel)
    assert _rows(session)[0] == (1, "one", 10)


def test_delete_rows_database_error_propagates(session):
    with patch.object(session, "exec", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            delete_rows_within_id_list([1], session, MockModel)


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
    assert empty == (True, 0)
    assert missing == (True, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_field", ["name", "nope"])
async def test_a_delete_rows_rejects_non_primary_key_field(
    a_session, bad_field
):
    with pytest.raises(ValueError):
        await a_delete_rows_within_id_list(
            [1], a_session, MockModel, pk_field=bad_field
        )
    assert len(await _a_rows(a_session)) == 4


@pytest.mark.asyncio
async def test_a_delete_rows_chunks_large_id_lists(a_session):
    ok, count = await a_delete_rows_within_id_list(
        [1, 2, 3, 4, 99], a_session, MockModel, chunk_size=2
    )
    assert (ok, count) == (True, 4)
    assert await _a_rows(a_session) == []


@pytest.mark.asyncio
async def test_a_bulk_update_sets_values(a_session):
    ok, count = await a_bulk_update_rows(
        [2, 3, 99], {"value": 7}, a_session, MockModel
    )
    assert (ok, count) == (True, 2)
    assert [r[2] for r in await _a_rows(a_session)] == [10, 7, 7, 40]


@pytest.mark.asyncio
async def test_a_bulk_update_validation_errors(a_session):
    with pytest.raises(ValueError):
        await a_bulk_update_rows([1], {}, a_session, MockModel)
    with pytest.raises(ValueError):
        await a_bulk_update_rows([1], {"nope": 1}, a_session, MockModel)
    with pytest.raises(ValueError):
        await a_bulk_update_rows([1], {"id": 9}, a_session, MockModel)
    assert (await _a_rows(a_session))[0] == (1, "one", 10)


@pytest.mark.asyncio
async def test_a_bulk_update_chunks_large_id_lists(a_session):
    ok, count = await a_bulk_update_rows(
        [1, 2, 3, 4], {"value": 5}, a_session, MockModel, chunk_size=3
    )
    assert (ok, count) == (True, 4)
    assert [r[2] for r in await _a_rows(a_session)] == [5, 5, 5, 5]


@pytest.mark.asyncio
async def test_a_bulk_update_database_error_rolls_back_and_raises(a_session):
    with pytest.raises(IntegrityError):
        await a_bulk_update_rows([1, 2], {"name": None}, a_session, MockModel)
    assert (await _a_rows(a_session))[0] == (1, "one", 10)


def _record(engine, verb):
    """Record the bind-parameter count of each ``verb`` statement sent."""
    params_per_statement = []

    @event.listens_for(engine, "before_cursor_execute")
    def _on_execute(conn, cursor, statement, parameters, *args):
        if statement.lstrip().upper().startswith(verb):
            params_per_statement.append(len(parameters))

    return params_per_statement


def test_delete_sends_one_statement_per_batch_not_per_row(session):
    seen = _record(session.get_bind(), "DELETE")
    delete_rows_within_id_list(
        [1, 2, 3, 4, 99], session, MockModel, chunk_size=2
    )
    assert seen == [2, 2, 1]


def test_update_sends_one_statement_per_batch_not_per_row(session):
    seen = _record(session.get_bind(), "UPDATE")
    bulk_update_rows(
        [1, 2, 3, 4, 99], {"value": 0}, session, MockModel, chunk_size=2
    )
    assert len(seen) == 3


@pytest.mark.asyncio
async def test_a_delete_sends_one_statement_per_batch_not_per_row(a_session):
    seen = _record(a_session.bind.sync_engine, "DELETE")
    await a_delete_rows_within_id_list(
        [1, 2, 3, 4, 99], a_session, MockModel, chunk_size=2
    )
    assert seen == [2, 2, 1]


@pytest.mark.asyncio
async def test_a_update_sends_one_statement_per_batch_not_per_row(a_session):
    seen = _record(a_session.bind.sync_engine, "UPDATE")
    await a_bulk_update_rows(
        [1, 2, 3, 4, 99], {"value": 0}, a_session, MockModel, chunk_size=2
    )
    assert len(seen) == 3
