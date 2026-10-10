"""
RedisCache hardening and invalidation gaps (issue #36, ADR-0012).
"""

import math
from typing import Optional

import pytest
import pytest_asyncio
from pydantic import field_serializer
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import Field, Session, SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

import sqlmodel_crud_utils as scu
from sqlmodel_crud_utils.cache import InMemoryCache, RedisCache, configure_cache
from sqlmodel_crud_utils.transactions import a_transaction, transaction


class FakePipeline:
    def __init__(self, client):
        self.client, self.ops = client, []

    def __getattr__(self, name):
        def queue(*a, **k):
            self.ops.append((name, a, k))
            return self

        return queue

    def execute(self):
        self.client.pipelines += 1
        for name, a, k in self.ops:
            getattr(self.client, name)(*a, **k)
        return []


class FakeRedis:
    """In-process stand-in recording TTLs (ms) and pipeline use."""

    def __init__(self):
        self.kv, self.sets, self.ttls = {}, {}, {}
        self.expiry, self.pipelines = {}, 0

    def pipeline(self, transaction=True):
        return FakePipeline(self)

    def get(self, k):
        return self.kv.get(k)

    def set(self, k, v, ex=None, px=None):
        self.kv[k] = v
        self.ttls[k] = px if px is not None else (ex or 0) * 1000

    def sadd(self, k, *v):
        self.sets.setdefault(k, set()).update(v)

    def pexpire(self, k, ms, nx=False, gt=False):
        cur = self.expiry.get(k)
        if nx and cur is not None:
            return
        if gt and cur is not None and ms <= cur:
            return
        if gt and cur is None and k in self.expiry:
            return
        self.expiry[k] = ms

    def smembers(self, k):
        return set(self.sets.get(k, ()))

    def delete(self, *ks):
        for k in ks:
            self.kv.pop(k, None)
            self.sets.pop(k, None)
            self.expiry.pop(k, None)

    def scan_iter(self, match=None):
        prefix = match.rstrip("*")
        return iter([k for k in list(self.kv) if k.startswith(prefix)])


def test_index_set_gets_a_ttl_covering_its_entries():
    fake = FakeRedis()
    cache = RedisCache(client=fake)
    cache.set("ns", "a", {"v": 1}, ttl=10)
    cache.set("ns", "b", {"v": 2}, ttl=100)
    cache.set("ns", "c", {"v": 3}, ttl=5)
    assert fake.expiry["scu:idx:ns"] >= 100_000


def test_set_and_index_are_one_transaction():
    fake = FakeRedis()
    RedisCache(client=fake).set("ns", "a", {"v": 1})
    assert fake.pipelines == 1
    assert "scu:ns:a" in fake.sets["scu:idx:ns"]


@pytest.mark.parametrize("ttl", [0, -1])
def test_zero_ttl_expires_immediately_like_memory(ttl):
    fake = FakeRedis()
    redis_cache = RedisCache(client=fake)
    mem = InMemoryCache()
    for cache in (redis_cache, mem):
        cache.set("ns", "k", {"v": 1})
        cache.set("ns", "k", {"v": 2}, ttl=ttl)
        assert cache.get("ns", "k") is None


def test_fractional_ttl_is_not_rounded_up_to_a_second():
    fake = FakeRedis()
    RedisCache(client=fake).set("ns", "k", {"v": 1}, ttl=0.25)
    assert fake.ttls["scu:ns:k"] == math.ceil(0.25 * 1000)


def test_async_client_is_rejected():
    class AsyncClient:
        async def get(self, k): ...

        async def set(self, k, v, **kw): ...

    with pytest.raises(TypeError, match="async"):
        RedisCache(client=AsyncClient())


class Shouty(SQLModel, table=True):
    __tablename__ = "hard_shouty"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = ""

    @field_serializer("name")
    def _upper(self, v):
        return v.upper()


class Plain(SQLModel, table=True):
    __tablename__ = "hard_plain"
    id: Optional[int] = Field(default=None, primary_key=True)
    n: int = 0


@pytest.fixture(autouse=True)
def backend():
    cache = InMemoryCache(default_ttl=60)
    configure_cache(cache)
    yield cache
    configure_cache(None)


@pytest.fixture
def sess(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'h.sqlite'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as s:
        yield s
    engine.dispose()


@pytest_asyncio.fixture
async def asess(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'ha.sqlite'}"
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    async with AsyncSession(engine, expire_on_commit=False) as s:
        yield s
    await engine.dispose()


def test_custom_field_serializer_does_not_change_cached_value(sess):
    scu.write_row(Shouty(id=1, name="abc"), sess)
    _, db = scu.get_row(1, sess, Shouty, use_cache=True)
    _, hit = scu.get_row(1, sess, Shouty, use_cache=True)
    assert db.name == hit.name == "abc"


@pytest.mark.asyncio
async def test_custom_field_serializer_async(asess):
    await scu.a_write_row(Shouty(id=1, name="abc"), asess)
    await scu.a_get_row(1, asess, Shouty, use_cache=True)
    _, hit = await scu.a_get_row(1, asess, Shouty, use_cache=True)
    assert hit.name == "abc"


def test_transaction_commit_invalidates(sess):
    scu.write_row(Plain(id=1, n=1), sess)
    scu.get_row(1, sess, Plain, use_cache=True)
    with transaction(sess) as tx:
        row = tx.get(Plain, 1)
        row.n = 2
        tx.add(row)
    _, row = scu.get_row(1, sess, Plain, use_cache=True)
    assert row.n == 2


@pytest.mark.asyncio
async def test_a_transaction_commit_invalidates(asess):
    await scu.a_write_row(Plain(id=1, n=1), asess)
    await scu.a_get_row(1, asess, Plain, use_cache=True)
    async with a_transaction(asess) as tx:
        row = await tx.get(Plain, 1)
        row.n = 2
        tx.add(row)
    _, row = await scu.a_get_row(1, asess, Plain, use_cache=True)
    assert row.n == 2


def test_transaction_rollback_leaves_cache_correct(sess):
    scu.write_row(Plain(id=1, n=1), sess)
    scu.get_row(1, sess, Plain, use_cache=True)
    with pytest.raises(scu.TransactionError):
        with transaction(sess) as tx:
            tx.get(Plain, 1).n = 9
            tx.flush()
            raise ValueError("x")
    _, row = scu.get_row(1, sess, Plain, use_cache=True)
    assert row.n == 1


def test_real_async_redis_client_is_rejected():
    aredis = pytest.importorskip("redis.asyncio")
    with pytest.raises(TypeError, match="async"):
        RedisCache(client=aredis.Redis())
