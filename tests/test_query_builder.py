"""
Real-SQLite tests for the fluent query builder (issue #23, ADR-0010).
"""

import pytest
import pytest_asyncio
from sqlalchemy import create_engine, or_
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import selectinload
from sqlmodel import Session, SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

import sqlmodel_crud_utils
from sqlmodel_crud_utils import AsyncQueryBuilder, QueryBuilder

from .models import MockModel, MockRelatedModel


def _seed():
    parent = MockRelatedModel(id=1, related_name="parent")
    rows = [
        MockModel(id=i, name=f"row-{i}", value=i * 10, related_field_id=1)
        for i in range(1, 6)
    ]
    return [parent, *rows]


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'qb.sqlite'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as sess:
        sess.add_all(_seed())
        sess.commit()
        yield sess
    engine.dispose()


@pytest_asyncio.fixture
async def async_session(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'qb_async.sqlite'}"
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    async with AsyncSession(engine, expire_on_commit=False) as sess:
        sess.add_all(_seed())
        await sess.commit()
        yield sess
    await engine.dispose()


def _ids(rows):
    return [r.id for r in rows]


def test_builders_are_exported_from_package_and_modules():
    from sqlmodel_crud_utils import a_sync, sync

    assert sync.QueryBuilder is QueryBuilder
    assert a_sync.AsyncQueryBuilder is AsyncQueryBuilder
    for name in ("QueryBuilder", "AsyncQueryBuilder"):
        assert name in sqlmodel_crud_utils.__all__


def test_all_returns_every_row(session):
    ok, rows = QueryBuilder(session, MockModel).order_by("id").all()
    assert ok is True
    assert _ids(rows) == [1, 2, 3, 4, 5]


def test_all_empty_result(session):
    ok, rows = QueryBuilder(session, MockModel).where(name="missing").all()
    assert (ok, rows) == (False, [])


def test_where_kwargs_and_expressions_combine(session):
    ok, rows = (
        QueryBuilder(session, MockModel)
        .where(MockModel.value >= 20, MockModel.value <= 40)
        .where(name="row-3")
        .all()
    )
    assert ok is True
    assert _ids(rows) == [3]


def test_where_or_expression(session):
    _, rows = (
        QueryBuilder(session, MockModel)
        .where(or_(MockModel.id == 1, MockModel.id == 5))
        .order_by("id")
        .all()
    )
    assert _ids(rows) == [1, 5]


def test_where_unknown_field_raises(session):
    with pytest.raises(ValueError):
        QueryBuilder(session, MockModel).where(nope=1)


def test_order_by_name_expression_and_desc(session):
    _, rows = (
        QueryBuilder(session, MockModel).order_by("value", desc=True).all()
    )
    assert _ids(rows) == [5, 4, 3, 2, 1]
    _, rows = QueryBuilder(session, MockModel).order_by(MockModel.value).all()
    assert _ids(rows) == [1, 2, 3, 4, 5]


def test_order_by_unknown_field_raises(session):
    with pytest.raises(ValueError):
        QueryBuilder(session, MockModel).order_by("nope")


def test_limit_and_offset(session):
    _, rows = QueryBuilder(session, MockModel).order_by("id").limit(2).all()
    assert _ids(rows) == [1, 2]
    _, rows = (
        QueryBuilder(session, MockModel).order_by("id").limit(2).offset(3).all()
    )
    assert _ids(rows) == [4, 5]


@pytest.mark.parametrize("bad", [-1, "3", 1.5, True])
def test_limit_offset_reject_invalid(session, bad):
    with pytest.raises(ValueError):
        QueryBuilder(session, MockModel).limit(bad)
    with pytest.raises(ValueError):
        QueryBuilder(session, MockModel).offset(bad)


def test_first(session):
    ok, row = QueryBuilder(session, MockModel).order_by("id", desc=True).first()
    assert ok is True
    assert row.id == 5


def test_first_empty_result(session):
    assert QueryBuilder(session, MockModel).where(name="missing").first() == (
        False,
        None,
    )


def test_count(session):
    assert QueryBuilder(session, MockModel).count() == (True, 5)
    assert QueryBuilder(session, MockModel).where(
        MockModel.value > 20
    ).count() == (
        True,
        3,
    )


def test_count_empty_result(session):
    assert QueryBuilder(session, MockModel).where(name="missing").count() == (
        False,
        0,
    )


def test_count_respects_limit_and_offset(session):
    qb = QueryBuilder(session, MockModel).order_by("id").limit(2).offset(4)
    assert qb.count() == (True, 1)


def test_builders_are_immutable(session):
    base = QueryBuilder(session, MockModel)
    narrowed = base.where(name="row-1")
    assert base.count() == (True, 5)
    assert narrowed.count() == (True, 1)


def test_composes_with_caller_stmnt(session):
    stmnt = select(MockModel).where(MockModel.value > 10)
    _, rows = (
        QueryBuilder(session, MockModel, stmnt=stmnt)
        .where(MockModel.value < 50)
        .order_by("id")
        .all()
    )
    assert _ids(rows) == [2, 3, 4]


def test_caller_stmnt_loader_options_are_preserved(session):
    stmnt = select(MockModel).options(selectinload(MockModel.related_field))
    _, rows = QueryBuilder(session, MockModel, stmnt=stmnt).order_by("id").all()
    session.expunge_all()
    assert "related_field" in rows[0].__dict__
    assert rows[0].related_field.related_name == "parent"


@pytest.mark.asyncio
async def test_async_full_surface(async_session):
    qb = AsyncQueryBuilder(async_session, MockModel)
    ok, rows = await qb.order_by("id").all()
    assert (ok, _ids(rows)) == (True, [1, 2, 3, 4, 5])

    assert await qb.where(name="missing").all() == (False, [])
    assert await qb.where(name="missing").first() == (False, None)
    assert await qb.where(name="missing").count() == (False, 0)

    ok, rows = await (
        qb.where(MockModel.value >= 20, name="row-3").order_by("id").all()
    )
    assert _ids(rows) == [3]

    _, rows = await qb.order_by("value", desc=True).limit(2).offset(1).all()
    assert _ids(rows) == [4, 3]

    ok, row = await qb.order_by("id", desc=True).first()
    assert (ok, row.id) == (True, 5)
    assert await qb.count() == (True, 5)
    assert await qb.order_by("id").limit(2).offset(4).count() == (True, 1)


@pytest.mark.asyncio
async def test_async_composes_with_caller_stmnt(async_session):
    stmnt = select(MockModel).options(selectinload(MockModel.related_field))
    _, rows = await (
        AsyncQueryBuilder(async_session, MockModel, stmnt=stmnt)
        .where(MockModel.value > 30)
        .order_by("id")
        .all()
    )
    assert _ids(rows) == [4, 5]
    assert rows[0].related_field.related_name == "parent"
