"""
Opt-in read caching (ADR-0012, issue #25), run against real SQLite for the
sync and async APIs. A statement counter on the engine proves whether a read
reached the database.
"""

import time

import pytest
import pytest_asyncio
from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import Session, SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

import sqlmodel_crud_utils as scu
from sqlmodel_crud_utils.cache import (
    CacheBackend,
    InMemoryCache,
    RedisCache,
    configure_cache,
    invalidate_cache,
)

from .models import MockModel


class Counter:
    def __init__(self):
        self.selects = 0

    def __call__(self, conn, cursor, statement, *args):
        if statement.lstrip().upper().startswith("SELECT"):
            self.selects += 1


@pytest.fixture(autouse=True)
def backend():
    cache = InMemoryCache(default_ttl=60)
    configure_cache(cache)
    yield cache
    configure_cache(None)


@pytest.fixture
def sync_env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'c.sqlite'}")
    SQLModel.metadata.create_all(engine)
    counter = Counter()
    with Session(engine, expire_on_commit=False) as sess:
        sess.add_all(
            [MockModel(id=i, name=f"n{i}", value=i) for i in range(1, 6)]
        )
        sess.commit()
        event.listen(engine, "before_cursor_execute", counter)
        yield sess, counter
    engine.dispose()


@pytest_asyncio.fixture
async def async_env(tmp_path):
    path = tmp_path / "ca.sqlite"
    sync_engine = create_engine(f"sqlite:///{path}")
    SQLModel.metadata.create_all(sync_engine)
    with Session(sync_engine) as s:
        s.add_all([MockModel(id=i, name=f"n{i}", value=i) for i in range(1, 6)])
        s.commit()
    sync_engine.dispose()
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    counter = Counter()
    event.listen(engine.sync_engine, "before_cursor_execute", counter)
    async with AsyncSession(engine, expire_on_commit=False) as sess:
        yield sess, counter
    await engine.dispose()


def test_default_is_uncached(sync_env):
    sess, counter = sync_env
    scu.get_row(1, sess, MockModel)
    scu.get_row(1, sess, MockModel)
    assert counter.selects == 2


def test_get_row_hit_skips_database(sync_env):
    sess, counter = sync_env
    ok, first = scu.get_row(1, sess, MockModel, use_cache=True)
    ok2, second = scu.get_row(1, sess, MockModel, use_cache=True)
    assert ok and ok2
    assert counter.selects == 1
    assert second.name == first.name == "n1"
    assert isinstance(second, MockModel)


def test_misses_are_not_cached(sync_env):
    sess, counter = sync_env
    assert scu.get_row(99, sess, MockModel, use_cache=True) == (False, None)
    scu.write_row(MockModel(id=99, name="late"), sess)
    ok, row = scu.get_row(99, sess, MockModel, use_cache=True)
    assert ok and row.name == "late"


def test_get_rows_hit_and_distinct_keys(sync_env):
    sess, counter = sync_env
    scu.get_rows(sess, MockModel, name="n1", use_cache=True)
    scu.get_rows(sess, MockModel, name="n1", use_cache=True)
    assert counter.selects == 1
    ok, rows = scu.get_rows(sess, MockModel, name="n2", use_cache=True)
    assert counter.selects == 2
    assert [r.name for r in rows] == ["n2"]
    scu.get_rows(sess, MockModel, page_size=2, use_cache=True)
    scu.get_rows(sess, MockModel, page_size=3, use_cache=True)
    assert counter.selects == 4


def test_get_rows_custom_stmnt_bypasses_cache(sync_env):
    sess, counter = sync_env
    stmnt = select(MockModel)
    scu.get_rows(sess, MockModel, stmnt=stmnt, use_cache=True)
    scu.get_rows(sess, MockModel, stmnt=stmnt, use_cache=True)
    assert counter.selects == 2


def _prime(sess):
    scu.get_row(1, sess, MockModel, use_cache=True)
    scu.get_rows(sess, MockModel, use_cache=True)


def _fresh(sess, counter):
    before = counter.selects
    scu.get_row(1, sess, MockModel, use_cache=True)
    scu.get_rows(sess, MockModel, use_cache=True)
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
    assert _fresh(sess, counter) == 2


def test_bulk_update_value_is_visible_after_invalidation(sync_env):
    sess, _ = sync_env
    scu.get_row(1, sess, MockModel, use_cache=True)
    scu.bulk_update_rows([1], {"name": "fresh"}, sess, MockModel)
    ok, row = scu.get_row(1, sess, MockModel, use_cache=True)
    assert row.name == "fresh"


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


def test_invalidate_cache_public_api(sync_env):
    sess, counter = sync_env
    _prime(sess)
    invalidate_cache(MockModel)
    assert _fresh(sess, counter) == 2
    invalidate_cache()
    assert _fresh(sess, counter) == 2


def test_ttl_expiry(sync_env):
    sess, counter = sync_env
    scu.get_row(1, sess, MockModel, use_cache=True, cache_ttl=0.05)
    time.sleep(0.1)
    scu.get_row(1, sess, MockModel, use_cache=True, cache_ttl=0.05)
    assert counter.selects == 2


def test_different_databases_do_not_share_entries(tmp_path, sync_env):
    sess, _ = sync_env
    scu.get_row(1, sess, MockModel, use_cache=True)
    engine = create_engine(f"sqlite:///{tmp_path / 'other.sqlite'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as other:
        other.add(MockModel(id=1, name="other-db"))
        other.commit()
        ok, row = scu.get_row(1, other, MockModel, use_cache=True)
    engine.dispose()
    assert row.name == "other-db"


def test_in_memory_sqlite_engines_do_not_share_entries():
    rows = []
    for label in ("A", "B"):
        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)
        with Session(engine) as other:
            other.add(MockModel(id=1, name=label))
            other.commit()
            rows.append(scu.get_row(1, other, MockModel, use_cache=True)[1])
        engine.dispose()
    assert [r.name for r in rows] == ["A", "B"]


def test_no_backend_use_cache_is_noop(sync_env):
    configure_cache(None)
    sess, counter = sync_env
    scu.get_row(1, sess, MockModel, use_cache=True)
    scu.get_row(1, sess, MockModel, use_cache=True)
    assert counter.selects == 2


def test_in_memory_backend_unit():
    cache = InMemoryCache(default_ttl=60, max_entries=2)
    assert isinstance(cache, CacheBackend)
    cache.set("ns", "a", {"v": 1})
    cache.set("ns", "b", {"v": 2})
    cache.set("ns", "c", {"v": 3})
    assert cache.get("ns", "a") is None
    assert cache.get("ns", "c") == {"v": 3}
    cache.invalidate("ns")
    assert cache.get("ns", "c") is None


class FakeRedis:
    """Minimal in-process stand-in for the redis client calls used."""

    def __init__(self):
        self.kv, self.sets, self.ttls = {}, {}, {}

    def get(self, k):
        return self.kv.get(k)

    def set(self, k, v, ex=None):
        self.kv[k] = v
        self.ttls[k] = ex

    def sadd(self, k, *v):
        self.sets.setdefault(k, set()).update(v)

    def smembers(self, k):
        return set(self.sets.get(k, ()))

    def delete(self, *ks):
        for k in ks:
            self.kv.pop(k, None)
            self.sets.pop(k, None)

    def scan_iter(self, match=None):
        prefix = match.rstrip("*")
        return iter([k for k in list(self.kv) if k.startswith(prefix)])


def test_redis_backend_roundtrip_with_client():
    fake = FakeRedis()
    cache = RedisCache(client=fake, default_ttl=30)
    assert cache.blocking is True
    cache.set("ns", "k", {"a": [1, 2]})
    assert cache.get("ns", "k") == {"a": [1, 2]}
    assert 30 in fake.ttls.values()
    cache.set("other", "k", {"a": 0})
    cache.invalidate("ns")
    assert cache.get("ns", "k") is None
    assert cache.get("other", "k") == {"a": 0}
    cache.clear()
    assert cache.get("other", "k") is None


def test_redis_backend_without_extra_raises_clear_error(monkeypatch):
    import builtins

    real = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "redis":
            raise ImportError("no redis")
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(ImportError, match="cache"):
        RedisCache(url="redis://localhost")


def test_public_exports():
    for name in (
        "CacheBackend",
        "InMemoryCache",
        "RedisCache",
        "configure_cache",
        "invalidate_cache",
    ):
        assert name in scu.__all__
        assert hasattr(scu, name)


@pytest.mark.asyncio
async def test_async_get_row_and_get_rows_hit(async_env):
    sess, counter = async_env
    await scu.a_get_row(1, sess, MockModel, use_cache=True)
    ok, row = await scu.a_get_row(1, sess, MockModel, use_cache=True)
    assert ok and row.name == "n1" and counter.selects == 1
    await scu.a_get_rows(sess, MockModel, name="n1", use_cache=True)
    await scu.a_get_rows(sess, MockModel, name="n1", use_cache=True)
    assert counter.selects == 2


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


@pytest.mark.asyncio
@pytest.mark.parametrize("name", sorted(A_WRITES))
async def test_async_every_write_invalidates(async_env, name):
    sess, counter = async_env
    await scu.a_get_row(1, sess, MockModel, use_cache=True)
    await scu.a_get_rows(sess, MockModel, use_cache=True)
    before = counter.selects
    await scu.a_get_row(1, sess, MockModel, use_cache=True)
    assert counter.selects == before
    await A_WRITES[name](sess)
    before = counter.selects
    await scu.a_get_row(1, sess, MockModel, use_cache=True)
    await scu.a_get_rows(sess, MockModel, use_cache=True)
    assert counter.selects - before == 2


@pytest.mark.asyncio
async def test_async_blocking_backend_runs_off_loop(async_env):
    fake = FakeRedis()
    configure_cache(RedisCache(client=fake, default_ttl=30))
    sess, counter = async_env
    await scu.a_get_row(1, sess, MockModel, use_cache=True)
    await scu.a_get_row(1, sess, MockModel, use_cache=True)
    assert counter.selects == 1


def test_uncacheable_row_is_returned_not_raised(tmp_path):
    from typing import Optional

    from sqlmodel import Field

    class Blob(SQLModel, table=True):
        __tablename__ = "cache_blob"
        id: Optional[int] = Field(default=None, primary_key=True)
        data: bytes = b""

    engine = create_engine(f"sqlite:///{tmp_path / 'b.sqlite'}")
    SQLModel.metadata.create_all(engine, tables=[Blob.__table__])
    with Session(engine) as sess:
        sess.add(Blob(id=1, data=bytes([255, 254])))
        sess.commit()
        ok, row = scu.get_row(1, sess, Blob, use_cache=True)
        ok2, rows = scu.get_rows(sess, Blob, use_cache=True)
    engine.dispose()
    assert ok and ok2 and row.data == bytes([255, 254]) and len(rows) == 1
