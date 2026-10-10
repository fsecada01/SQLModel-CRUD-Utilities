"""
Real-SQLite tests for the fluent query builder (issue #23, ADR-0010).
"""

import pytest
import pytest_asyncio
from sqlalchemy import create_engine, or_
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import joinedload, selectinload
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


def test_first_honors_limit_zero(session):
    qb = QueryBuilder(session, MockModel).limit(0)
    assert qb.all() == (False, [])
    assert qb.first() == (False, None)


def test_first_without_limit_still_returns_one_row(session):
    ok, row = QueryBuilder(session, MockModel).order_by("id").first()
    assert (ok, row.id) == (True, 1)


def test_order_by_desc_rejects_expression_with_direction(session):
    qb = QueryBuilder(session, MockModel)
    with pytest.raises(ValueError, match="direction"):
        qb.order_by(MockModel.value.desc(), desc=True)
    with pytest.raises(ValueError, match="direction"):
        qb.order_by("id", MockModel.value.asc(), desc=True)


def test_order_by_desc_accepts_plain_expression(session):
    _, rows = (
        QueryBuilder(session, MockModel)
        .order_by(MockModel.value, desc=True)
        .all()
    )
    assert _ids(rows) == [5, 4, 3, 2, 1]


def test_all_with_joinedload_collection_stmnt(session):
    stmnt = select(MockRelatedModel).options(
        joinedload(MockRelatedModel.mock_models)
    )
    ok, rows = QueryBuilder(session, MockRelatedModel, stmnt=stmnt).all()
    assert ok is True
    assert [r.id for r in rows] == [1]
    assert len(rows[0].mock_models) == 5


@pytest.mark.asyncio
async def test_async_first_honors_limit_zero(async_session):
    qb = AsyncQueryBuilder(async_session, MockModel).limit(0)
    assert await qb.all() == (False, [])
    assert await qb.first() == (False, None)


@pytest.mark.asyncio
async def test_async_order_by_desc_rejects_expression_with_direction(
    async_session,
):
    qb = AsyncQueryBuilder(async_session, MockModel)
    with pytest.raises(ValueError, match="direction"):
        qb.order_by(MockModel.value.desc(), desc=True)


@pytest.mark.asyncio
async def test_async_all_with_joinedload_collection_stmnt(async_session):
    stmnt = select(MockRelatedModel).options(
        joinedload(MockRelatedModel.mock_models)
    )
    ok, rows = await AsyncQueryBuilder(
        async_session, MockRelatedModel, stmnt=stmnt
    ).all()
    assert ok is True
    assert [r.id for r in rows] == [1]


# --- #37: loader methods and suffix filters ---------------------------------


def _loaded(obj, attr):
    from sqlalchemy import inspect as sa_inspect

    return attr in sa_inspect(obj).dict


def test_selectin_loads_relationship_without_stmnt(session):
    session.expunge_all()
    ok, rows = QueryBuilder(session, MockModel).selectin("related_field").all()
    assert ok and all(_loaded(r, "related_field") for r in rows)


def test_lazy_leaves_relationship_unloaded(session):
    session.expunge_all()
    ok, rows = QueryBuilder(session, MockModel).lazy("related_field").all()
    assert ok and not any(_loaded(r, "related_field") for r in rows)


def test_loader_methods_are_immutable_and_chain(session):
    base = QueryBuilder(session, MockModel)
    derived = base.selectin("related_field")
    assert derived is not base
    assert base._stmnt is not derived._stmnt
    assert derived.where(id=1).count() == (True, 1)


def test_loader_rejects_unknown_relationship(session):
    with pytest.raises(ValueError):
        QueryBuilder(session, MockModel).selectin("nope")
    with pytest.raises(ValueError):
        QueryBuilder(session, MockModel).lazy("name")


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        ({"value__gte": 30}, [3, 4, 5]),
        ({"value__gt": 30}, [4, 5]),
        ({"value__lte": 20}, [1, 2]),
        ({"value__lt": 20}, [1]),
        ({"name__like": "row-3"}, [3]),
        ({"id__in": [1, 5]}, [1, 5]),
        ({"value__gte": 20, "value__lt": 50}, [2, 3, 4]),
    ],
)
def test_suffix_filters(session, filters, expected):
    ok, rows = (
        QueryBuilder(session, MockModel).where(**filters).order_by("id").all()
    )
    assert _ids(rows) == expected


def test_suffix_filter_errors(session):
    qb = QueryBuilder(session, MockModel)
    with pytest.raises(ValueError):
        qb.where(nope__gte=1)
    with pytest.raises(ValueError):
        qb.where(id__in=5)
    with pytest.raises(ValueError):
        qb.where(value__bogus=1)


def test_exact_equality_still_works_with_suffix_support(session):
    assert QueryBuilder(session, MockModel).where(id=2).count() == (True, 1)


@pytest.mark.asyncio
async def test_async_selectin_and_suffix_filters(async_session):
    ok, rows = await (
        AsyncQueryBuilder(async_session, MockModel)
        .selectin("related_field")
        .where(value__gte=40)
        .order_by("id")
        .all()
    )
    assert _ids(rows) == [4, 5]
    assert all(_loaded(r, "related_field") for r in rows)
    ok, rows = await (
        AsyncQueryBuilder(async_session, MockModel)
        .lazy("related_field")
        .where(id__in=[1])
        .all()
    )
    assert _ids(rows) == [1]
    with pytest.raises(ValueError):
        AsyncQueryBuilder(async_session, MockModel).selectin("nope")
