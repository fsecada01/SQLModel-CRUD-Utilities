"""
Query builder caching (ADR-0015, issue #38), against real SQLite for the sync
and async builders. A statement counter on the engine proves whether a
terminal reached the database.
"""

import time
from typing import Optional

import pytest
import pytest_asyncio
from sqlalchemy import (
    Column,
    Integer,
    TypeDecorator,
    create_engine,
    event,
    literal_column,
    select,
    text,
)
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import Field, Session, SQLModel
from sqlmodel import select as sql_select
from sqlmodel.ext.asyncio.session import AsyncSession

import sqlmodel_crud_utils as scu
from sqlmodel_crud_utils import AsyncQueryBuilder, QueryBuilder
from sqlmodel_crud_utils.cache import (
    InMemoryCache,
    RedisCache,
    configure_cache,
    invalidate_cache,
)

from .models import MockModel, MockRelatedModel
from .test_cache_hardening import FakeRedis


class QbHidden(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    token: str = Field(default="", exclude=True)


class Probe:
    """A bind value whose ``repr`` says nothing about its content."""

    def __init__(self, v):
        self.v = v

    def __repr__(self):
        return "Probe"


class ProbeType(TypeDecorator):
    impl = Integer
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return value.v if isinstance(value, Probe) else value


class QbProbe(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    score: int = Field(sa_column=Column(ProbeType, nullable=False))


class Counter:
    def __init__(self):
        self.selects = 0

    def __call__(self, conn, cursor, statement, *args):
        if statement.lstrip().upper().startswith("SELECT"):
            self.selects += 1


def _seed():
    return [
        MockRelatedModel(id=1, related_name="parent"),
        *[
            MockModel(id=i, name=f"n{i}", value=i, related_field_id=1)
            for i in range(1, 6)
        ],
    ]


@pytest.fixture(autouse=True)
def backend():
    cache = InMemoryCache(default_ttl=60)
    configure_cache(cache)
    yield cache
    configure_cache(None)


@pytest.fixture
def sync_env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'qb.sqlite'}")
    SQLModel.metadata.create_all(engine)
    counter = Counter()
    with Session(engine, expire_on_commit=False) as sess:
        sess.add_all(_seed())
        sess.commit()
        sess.info.pop("sqlmodel_crud_utils.cache.touched", None)
        event.listen(engine, "before_cursor_execute", counter)
        yield sess, counter
    engine.dispose()


@pytest_asyncio.fixture
async def async_env(tmp_path):
    path = tmp_path / "qba.sqlite"
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    counter = Counter()
    async with AsyncSession(engine, expire_on_commit=False) as sess:
        sess.add_all(_seed())
        await sess.commit()
        sess.sync_session.info.pop("sqlmodel_crud_utils.cache.touched", None)
        event.listen(engine.sync_engine, "before_cursor_execute", counter)
        yield sess, counter
    await engine.dispose()


def _qb(sess):
    return QueryBuilder(sess, MockModel)


def _cached(sess, **kw):
    return QueryBuilder(sess, MockModel).cached(**kw)


# --- hits, misses, keys (sync) -------------------------------------------


def test_builder_is_uncached_by_default(sync_env):
    sess, counter = sync_env
    _qb(sess).where(name="n1").all()
    _qb(sess).where(name="n1").all()
    assert counter.selects == 2


def test_cached_returns_new_builder_and_leaves_original_uncached(sync_env):
    sess, counter = sync_env
    base = _qb(sess).where(name="n1")
    cached = base.cached()
    assert cached is not base
    base.all()
    base.all()
    assert counter.selects == 2
    cached.all()
    cached.all()
    assert counter.selects == 3


def test_cached_survives_further_chaining(sync_env):
    sess, counter = sync_env
    q = _cached(sess).where(value__gte=2).order_by("id").limit(3)
    q.all()
    q.all()
    assert counter.selects == 1


def test_all_hit_skips_database_and_returns_detached_instances(sync_env):
    sess, counter = sync_env
    ok, first = _cached(sess).order_by("id").all()
    ok2, second = _cached(sess).order_by("id").all()
    assert ok and ok2 and counter.selects == 1
    assert [r.name for r in second] == [r.name for r in first]
    assert all(isinstance(r, MockModel) for r in second)
    assert all(r in sess for r in first)
    assert all(r not in sess for r in second)


def test_first_hit_skips_database(sync_env):
    sess, counter = sync_env
    ok, row = _cached(sess).order_by("id").first()
    ok2, again = _cached(sess).order_by("id").first()
    assert ok and ok2 and counter.selects == 1
    assert again.id == row.id == 1
    assert isinstance(again, MockModel)


def test_count_hit_skips_database(sync_env):
    sess, counter = sync_env
    assert _cached(sess).where(value__gt=2).count() == (True, 3)
    assert _cached(sess).where(value__gt=2).count() == (True, 3)
    assert counter.selects == 1


def test_different_statements_have_different_keys(sync_env):
    sess, counter = sync_env
    assert [r.id for r in _cached(sess).where(name="n1").all()[1]] == [1]
    assert [r.id for r in _cached(sess).where(name="n2").all()[1]] == [2]
    assert [r.id for r in _cached(sess).order_by("id").all()[1]][0] == 1
    desc = _cached(sess).order_by("id", desc=True).all()[1]
    assert desc[0].id == 5
    assert len(_cached(sess).order_by("id").limit(2).all()[1]) == 2
    assert len(_cached(sess).order_by("id").limit(3).all()[1]) == 3
    paged = _cached(sess).order_by("id").limit(2).offset(2).all()[1]
    assert [r.id for r in paged] == [3, 4]
    assert counter.selects == 7


def test_operators_and_in_lists_do_not_collide(sync_env):
    sess, _ = sync_env
    ge = _cached(sess).where(value__gte=3).count()
    gt = _cached(sess).where(value__gt=3).count()
    lt = _cached(sess).where(value__lt=3).count()
    in_a = _cached(sess).where(value__in=[1, 2]).count()
    in_b = _cached(sess).where(value__in=[1, 2, 3]).count()
    assert (ge[1], gt[1], lt[1], in_a[1], in_b[1]) == (3, 2, 2, 2, 3)


def test_first_count_and_all_are_separate_entries(sync_env):
    sess, counter = sync_env
    q = _cached(sess).order_by("id").limit(3)
    assert len(q.all()[1]) == 3
    assert q.first()[1].id == 1
    assert q.count() == (True, 3)
    assert counter.selects == 3


def test_count_honours_limit_in_key(sync_env):
    sess, _ = sync_env
    assert _cached(sess).limit(2).count() == (True, 2)
    assert _cached(sess).limit(4).count() == (True, 4)
    assert _cached(sess).count() == (True, 5)


def test_empty_results_are_not_cached(sync_env):
    sess, counter = sync_env
    q = _cached(sess).where(name="late")
    assert q.all() == (False, [])
    assert q.first() == (False, None)
    assert q.count() == (False, 0)
    scu.write_row(MockModel(id=99, name="late"), sess)
    assert q.all()[1][0].id == 99
    assert q.first()[1].id == 99
    assert q.count() == (True, 1)


def test_ttl_expiry_and_ttl_validation(sync_env):
    sess, counter = sync_env
    q = _cached(sess, ttl=0.05).where(name="n1")
    q.all()
    time.sleep(0.1)
    q.all()
    assert counter.selects == 2
    for bad in (-1, True, "10"):
        with pytest.raises(ValueError):
            _qb(sess).cached(ttl=bad)


def test_no_backend_cached_is_noop(sync_env):
    configure_cache(None)
    sess, counter = sync_env
    _cached(sess).all()
    _cached(sess).all()
    assert counter.selects == 2


def test_different_databases_do_not_share_entries(tmp_path, sync_env):
    sess, _ = sync_env
    assert _cached(sess).where(id=1).first()[1].name == "n1"
    engine = create_engine(f"sqlite:///{tmp_path / 'other.sqlite'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as other:
        other.add(MockModel(id=1, name="other-db"))
        other.commit()
        row = QueryBuilder(other, MockModel).cached().where(id=1).first()[1]
    engine.dispose()
    assert row.name == "other-db"


# --- bypass rules ---------------------------------------------------------


def test_caller_stmnt_bypasses_cache(sync_env):
    sess, counter = sync_env
    q = QueryBuilder(sess, MockModel, sql_select(MockModel)).cached()
    q.all()
    q.all()
    q.where(name="n1").count()
    q.where(name="n1").count()
    assert counter.selects == 4


def test_selectin_and_lazy_bypass_cache(sync_env):
    sess, counter = sync_env
    for q in (
        _cached(sess).selectin("related_field"),
        _cached(sess).lazy("related_field"),
        _cached(sess).where(id=1).selectin("related_field"),
    ):
        before = counter.selects
        q.all()
        q.all()
        assert counter.selects - before >= 2


def test_selectin_results_keep_relationships_when_cached_flag_set(sync_env):
    sess, _ = sync_env
    ok, rows = _cached(sess).selectin("related_field").all()
    assert rows[0].related_field.related_name == "parent"
    ok, rows = _cached(sess).selectin("related_field").all()
    assert rows[0].related_field.related_name == "parent"


def test_statement_reading_another_table_bypasses_cache(sync_env):
    sess, counter = sync_env
    sub = select(MockRelatedModel.id).where(
        MockRelatedModel.related_name == "parent"
    )
    q = _cached(sess).where(MockModel.related_field_id.in_(sub))
    assert q.count() == (True, 5)
    assert q.count() == (True, 5)
    assert counter.selects == 2
    scu.update_row(1, {"related_name": "renamed"}, sess, MockRelatedModel)
    assert q.count() == (False, 0)


@pytest.mark.filterwarnings("ignore:SELECT statement has a cartesian")
def test_cross_table_where_clause_is_never_stale(sync_env):
    sess, _ = sync_env
    q = _cached(sess).where(MockRelatedModel.related_name == "parent")
    assert q.count() == (True, 5)
    scu.update_row(1, {"related_name": "renamed"}, sess, MockRelatedModel)
    assert q.count() == (False, 0)


def test_raw_text_and_literal_column_bypass_cache(sync_env):
    sess, counter = sync_env
    for q in (
        _cached(sess).where(text("value > 2")),
        _cached(sess).where(literal_column("value") > 2),
    ):
        before = counter.selects
        assert q.count() == (True, 3)
        assert q.count() == (True, 3)
        assert counter.selects - before == 2


def test_correlated_order_by_subquery_bypasses_cache(sync_env):
    sess, counter = sync_env
    order = (
        select(MockRelatedModel.id)
        .where(MockRelatedModel.id == MockModel.related_field_id)
        .scalar_subquery()
    )
    q = _cached(sess).order_by(order)
    q.all()
    q.all()
    assert counter.selects == 2


def test_same_table_subquery_is_cached(sync_env):
    sess, counter = sync_env
    sub = select(MockModel.id).where(MockModel.value > 3)
    q = _cached(sess).where(MockModel.id.in_(sub))
    assert q.count() == (True, 2)
    assert q.count() == (True, 2)
    assert counter.selects == 1


def test_bind_values_with_opaque_repr_are_not_cached(sync_env):
    sess, _ = sync_env
    sess.add_all([QbProbe(id=1, score=10), QbProbe(id=2, score=20)])
    sess.commit()
    qb = QueryBuilder(sess, QbProbe).cached()
    one = qb.where(QbProbe.score == Probe(10)).first()[1]
    two = qb.where(QbProbe.score == Probe(20)).first()[1]
    assert (one.id, two.id) == (1, 2)


def test_bind_value_types_are_distinct_keys(sync_env):
    sess, _ = sync_env
    q = _cached(sess)
    assert q.where(name="1").count() == (False, 0)
    assert q.where(value=1).count() == (True, 1)
    assert q.where(value=1.5).count() == (False, 0)


# --- field handling -------------------------------------------------------


def test_excluded_field_survives_a_cache_hit(sync_env):
    sess, _ = sync_env
    scu.write_row(QbHidden(id=1, token="hunter2"), sess)
    sess.expunge_all()
    qb = QueryBuilder(sess, QbHidden).cached()
    assert qb.all()[1][0].token == "hunter2"
    assert qb.all()[1][0].token == "hunter2"
    assert qb.first()[1].token == "hunter2"
    assert qb.first()[1].token == "hunter2"


# --- invalidation ---------------------------------------------------------


def _prime(sess):
    q = _cached(sess).order_by("id")
    q.all()
    q.first()
    q.count()


def _fresh(sess, counter):
    before = counter.selects
    _prime(sess)
    return counter.selects - before


WRITES = {
    "write_row": lambda s: scu.write_row(MockModel(id=50, name="x"), s),
    "insert_data_rows": lambda s: scu.insert_data_rows(
        [MockModel(id=51, name="y")], s
    ),
    "update_row": lambda s: scu.update_row(1, {"name": "z"}, s, MockModel),
    "delete_row": lambda s: scu.delete_row(2, s, MockModel),
    "get_one_or_create": lambda s: scu.get_one_or_create(
        s, MockModel, name="brand-new"
    ),
    "bulk_upsert_mappings": lambda s: scu.bulk_upsert_mappings(
        [{"id": 1, "name": "up"}], s, MockModel
    ),
    "bulk_update_rows": lambda s: scu.bulk_update_rows(
        [1], {"name": "bu"}, s, MockModel
    ),
    "delete_rows_within_id_list": lambda s: (
        scu.delete_rows_within_id_list([3], s, MockModel)
    ),
}


@pytest.mark.parametrize("name", sorted(WRITES))
def test_every_write_invalidates(sync_env, name):
    sess, counter = sync_env
    _prime(sess)
    assert _fresh(sess, counter) == 0
    WRITES[name](sess)
    assert _fresh(sess, counter) == 3


@pytest.mark.parametrize("name", sorted(WRITES))
def test_every_write_is_visible_to_the_next_read(sync_env, name):
    sess, _ = sync_env
    q = _cached(sess).order_by("id")
    before_ids = {r.id for r in q.all()[1]}
    before_count = q.count()[1]
    WRITES[name](sess)
    expected = {
        r.id
        for r in sess.exec(sql_select(MockModel).order_by(MockModel.id)).all()
    }
    assert {r.id for r in q.all()[1]} == expected
    assert q.count()[1] == len(expected)
    assert before_ids and before_count == 5


def test_updated_value_is_visible_after_bulk_update(sync_env):
    sess, _ = sync_env
    q = _cached(sess).where(id=1)
    assert q.first()[1].name == "n1"
    scu.bulk_update_rows([1], {"name": "fresh"}, sess, MockModel)
    assert q.first()[1].name == "fresh"
    assert q.all()[1][0].name == "fresh"


def test_failed_write_does_not_invalidate(sync_env):
    sess, counter = sync_env
    _prime(sess)
    ok, _ = scu.write_row(MockModel(id=1, name="dup"), sess)
    assert ok is False
    assert _fresh(sess, counter) == 0


def test_get_one_or_create_existing_keeps_cache(sync_env):
    sess, counter = sync_env
    _prime(sess)
    scu.get_one_or_create(sess, MockModel, name="n1")
    assert _fresh(sess, counter) == 0


def test_invalidate_cache_public_api_drops_builder_entries(sync_env):
    sess, counter = sync_env
    _prime(sess)
    invalidate_cache(MockModel)
    assert _fresh(sess, counter) == 3
    invalidate_cache()
    assert _fresh(sess, counter) == 3


def test_write_to_other_model_leaves_entries(sync_env):
    sess, counter = sync_env
    _prime(sess)
    scu.write_row(MockRelatedModel(id=7, related_name="other"), sess)
    assert _fresh(sess, counter) == 0


def test_transaction_invalidates_builder_entries(sync_env):
    sess, counter = sync_env
    _prime(sess)
    with scu.transaction(sess):
        sess.add(MockModel(id=60, name="tx"))
    assert _fresh(sess, counter) == 3
    assert _cached(sess).where(id=60).first()[1].name == "tx"


def test_rollback_after_cached_read_of_uncommitted_data(sync_env):
    sess, _ = sync_env
    row = sess.get(MockModel, 1)
    row.name = "uncommitted"
    q = _cached(sess).where(id=1)
    assert q.first()[1].name == "uncommitted"
    assert q.count() == (True, 1)
    sess.rollback()
    assert q.first()[1].name == "n1"


def test_rolled_back_insert_is_not_served(sync_env):
    sess, _ = sync_env
    sess.add(MockModel(id=70, name="ghost"))
    q = _cached(sess).where(id=70)
    assert q.count() == (True, 1)
    sess.rollback()
    assert q.count() == (False, 0)
    assert q.all() == (False, [])


# --- redis backend --------------------------------------------------------


def test_redis_backend_round_trip(sync_env):
    configure_cache(RedisCache(client=FakeRedis(), default_ttl=30))
    sess, counter = sync_env
    _cached(sess).where(name="n1").all()
    _cached(sess).where(name="n1").all()
    assert counter.selects == 1
    scu.update_row(1, {"name": "r"}, sess, MockModel)
    before = counter.selects
    _cached(sess).where(name="n1").all()
    assert counter.selects - before == 1


# --- async ---------------------------------------------------------------


def _aq(sess, **kw):
    return AsyncQueryBuilder(sess, MockModel).cached(**kw)


@pytest.mark.asyncio
async def test_async_default_is_uncached(async_env):
    sess, counter = async_env
    await AsyncQueryBuilder(sess, MockModel).all()
    await AsyncQueryBuilder(sess, MockModel).all()
    assert counter.selects == 2


@pytest.mark.asyncio
async def test_async_all_first_count_hit(async_env):
    sess, counter = async_env
    q = _aq(sess).order_by("id")
    ok, first = await q.all()
    ok2, second = await q.all()
    assert ok and ok2 and counter.selects == 1
    assert [r.name for r in second] == [r.name for r in first]
    assert all(r not in sess for r in second)
    assert (await q.first())[1].id == 1
    assert (await q.first())[1].id == 1
    assert await q.count() == (True, 5)
    assert await q.count() == (True, 5)
    assert counter.selects == 3


@pytest.mark.asyncio
async def test_async_distinct_statements_distinct_keys(async_env):
    sess, counter = async_env
    assert (await _aq(sess).where(name="n1").count()) == (True, 1)
    assert (await _aq(sess).where(name="n2").count()) == (True, 1)
    assert (await _aq(sess).limit(2).count()) == (True, 2)
    assert (await _aq(sess).limit(3).count()) == (True, 3)
    assert counter.selects == 4


@pytest.mark.asyncio
async def test_async_bypass_rules(async_env):
    sess, counter = async_env
    custom = AsyncQueryBuilder(sess, MockModel, sql_select(MockModel))
    await custom.cached().all()
    await custom.cached().all()
    assert counter.selects == 2
    q = _aq(sess).selectin("related_field")
    before = counter.selects
    await q.all()
    await q.all()
    assert counter.selects - before >= 2
    sub = select(MockRelatedModel.id).where(MockRelatedModel.id == 1)
    q = _aq(sess).where(MockModel.related_field_id.in_(sub))
    before = counter.selects
    await q.count()
    await q.count()
    assert counter.selects - before == 2


@pytest.mark.asyncio
async def test_async_empty_not_cached_and_excluded_field(async_env):
    sess, _ = async_env
    q = _aq(sess).where(name="late")
    assert await q.all() == (False, [])
    await scu.a_write_row(MockModel(id=99, name="late"), sess)
    assert (await q.all())[1][0].id == 99
    await scu.a_write_row(QbHidden(id=1, token="hunter2"), sess)
    sess.expunge_all()
    qb = AsyncQueryBuilder(sess, QbHidden).cached()
    await qb.all()
    assert (await qb.all())[1][0].token == "hunter2"
    await qb.first()
    assert (await qb.first())[1].token == "hunter2"


A_WRITES = {
    "write_row": lambda s: scu.a_write_row(MockModel(id=50, name="x"), s),
    "insert_data_rows": lambda s: scu.a_insert_data_rows(
        [MockModel(id=51, name="y")], s
    ),
    "update_row": lambda s: scu.a_update_row(1, {"name": "z"}, s, MockModel),
    "delete_row": lambda s: scu.a_delete_row(2, s, MockModel),
    "get_one_or_create": lambda s: scu.a_get_one_or_create(
        s, MockModel, name="brand-new"
    ),
    "bulk_upsert_mappings": lambda s: scu.a_bulk_upsert_mappings(
        [{"id": 1, "name": "up"}], s, MockModel
    ),
    "bulk_update_rows": lambda s: scu.a_bulk_update_rows(
        [1], {"name": "bu"}, s, MockModel
    ),
    "delete_rows_within_id_list": lambda s: scu.a_delete_rows_within_id_list(
        [3], s, MockModel
    ),
}


async def _a_prime(sess):
    q = _aq(sess).order_by("id")
    await q.all()
    await q.first()
    await q.count()


@pytest.mark.asyncio
@pytest.mark.parametrize("name", sorted(A_WRITES))
async def test_async_every_write_invalidates(async_env, name):
    sess, counter = async_env
    await _a_prime(sess)
    before = counter.selects
    await _a_prime(sess)
    assert counter.selects == before
    await A_WRITES[name](sess)
    before = counter.selects
    await _a_prime(sess)
    assert counter.selects - before == 3


@pytest.mark.asyncio
async def test_async_write_visible_to_next_read(async_env):
    sess, _ = async_env
    q = _aq(sess).where(id=1)
    assert (await q.first())[1].name == "n1"
    await scu.a_bulk_update_rows([1], {"name": "fresh"}, sess, MockModel)
    assert (await q.first())[1].name == "fresh"
    assert (await q.all())[1][0].name == "fresh"


@pytest.mark.asyncio
async def test_async_rollback_after_cached_read_of_uncommitted(async_env):
    sess, _ = async_env
    row = await sess.get(MockModel, 1)
    row.name = "uncommitted"
    q = _aq(sess).where(id=1)
    assert (await q.first())[1].name == "uncommitted"
    await sess.rollback()
    assert (await q.first())[1].name == "n1"


@pytest.mark.asyncio
async def test_async_blocking_backend_runs_off_loop(async_env):
    configure_cache(RedisCache(client=FakeRedis(), default_ttl=30))
    sess, counter = async_env
    q = _aq(sess).where(name="n1")
    await q.all()
    await q.all()
    await q.count()
    await q.count()
    assert counter.selects == 2
    await scu.a_update_row(1, {"name": "r"}, sess, MockModel)
    before = counter.selects
    await q.count()
    assert counter.selects - before == 1


@pytest.mark.asyncio
async def test_cached_ttl_validation_async(async_env):
    sess, _ = async_env
    with pytest.raises(ValueError):
        AsyncQueryBuilder(sess, MockModel).cached(ttl=-5)
