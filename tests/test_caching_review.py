"""
Regression tests for review findings on the caching layer (PR #34):
ORM-cascaded writes, generator inputs and excluded fields.
"""

from typing import Optional

import pytest
import pytest_asyncio
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import Field, Relationship, Session, SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from sqlmodel_crud_utils import a_sync as A
from sqlmodel_crud_utils import sync as S
from sqlmodel_crud_utils.cache import InMemoryCache, configure_cache


class CParent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    kids: list["CKid"] = Relationship(
        back_populates="parent",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class CKid(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    parent_id: Optional[int] = Field(default=None, foreign_key="cparent.id")
    parent: Optional[CParent] = Relationship(back_populates="kids")


class CHidden(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    token: str = Field(default="", exclude=True)


class CCounter(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    n: int = Field(default=0)


class CBounded(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    n: int = Field(default=0, ge=0)


@pytest.fixture(autouse=True)
def backend():
    configure_cache(InMemoryCache(default_ttl=60))
    yield
    configure_cache(None)


@pytest.fixture
def sess(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'r.sqlite'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as s:
        yield s
    engine.dispose()


@pytest_asyncio.fixture
async def a_sess(tmp_path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'ra.sqlite'}"
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    async with AsyncSession(engine, expire_on_commit=False) as s:
        yield s
    await engine.dispose()


def test_cascaded_insert_invalidates_child_model(sess):
    S.write_row(CParent(id=1), sess)
    assert not S.get_rows(sess, CKid, use_cache=True)[0]
    S.write_row(CParent(id=2, kids=[CKid(id=1)]), sess)
    assert len(S.get_rows(sess, CKid, use_cache=True)[1]) == 1
    S.write_row(CParent(id=3, kids=[CKid(id=2)]), sess)
    assert len(S.get_rows(sess, CKid, use_cache=True)[1]) == 2


def test_cascaded_delete_invalidates_child_model(sess):
    S.write_row(CParent(id=1, kids=[CKid(id=1), CKid(id=2)]), sess)
    assert len(S.get_rows(sess, CKid, use_cache=True)[1]) == 2
    assert S.delete_row(1, sess, CParent)
    assert not S.get_rows(sess, CKid, use_cache=True)[0]


def test_generator_insert_invalidates(sess):
    S.write_row(CParent(id=1), sess)
    S.get_rows(sess, CParent, use_cache=True)
    S.insert_data_rows((CParent(id=i) for i in (2, 3)), sess)
    assert len(S.get_rows(sess, CParent, use_cache=True)[1]) == 3


def test_rolled_back_flush_does_not_leak_into_later_invalidation(sess):
    S.write_row(CParent(id=1), sess)
    S.get_rows(sess, CKid, use_cache=True)
    sess.add(CKid(id=9))
    sess.flush()
    sess.rollback()
    S.write_row(CParent(id=2), sess)
    assert sess.info.get("sqlmodel_crud_utils.cache.touched") is None


def test_excluded_field_survives_a_cache_hit(sess):
    S.write_row(CHidden(id=1, token="hunter2"), sess)
    sess.expunge_all()
    assert S.get_row(1, sess, CHidden, use_cache=True)[1].token == "hunter2"
    assert S.get_row(1, sess, CHidden, use_cache=True)[1].token == "hunter2"
    assert S.get_rows(sess, CHidden, use_cache=True)[1][0].token == "hunter2"


@pytest.mark.asyncio
async def test_async_cascaded_insert_and_delete(a_sess):
    await A.write_row(CParent(id=1), a_sess)
    assert not (await A.get_rows(a_sess, CKid, use_cache=True))[0]
    await A.write_row(CParent(id=2, kids=[CKid(id=1)]), a_sess)
    assert len((await A.get_rows(a_sess, CKid, use_cache=True))[1]) == 1
    assert await A.delete_row(2, a_sess, CParent)
    assert not (await A.get_rows(a_sess, CKid, use_cache=True))[0]


@pytest.mark.asyncio
async def test_async_excluded_field_survives_a_cache_hit(a_sess):
    await A.write_row(CHidden(id=1, token="hunter2"), a_sess)
    a_sess.expunge_all()
    await A.get_row(1, a_sess, CHidden, use_cache=True)
    hit = (await A.get_row(1, a_sess, CHidden, use_cache=True))[1]
    assert hit.token == "hunter2"


def test_rollback_after_cached_read_of_uncommitted_data(sess):
    S.write_row(CCounter(id=1, n=1), sess)
    b = sess.get(CCounter, 1)
    b.n = 99
    assert S.get_row(1, sess, CCounter, use_cache=True)[1].n == 99
    sess.rollback()
    assert S.get_row(1, sess, CCounter, use_cache=True)[1].n == 1


def test_failed_update_commit_does_not_leave_uncommitted_read_cached(sess):
    S.write_row(CCounter(id=1, n=1), sess)
    sess.get(CCounter, 1).n = 99
    assert S.get_row(1, sess, CCounter, use_cache=True)[1].n == 99
    ok, _ = S.update_row(1, {"n": None}, sess, CCounter)
    assert not ok
    assert S.get_row(1, sess, CCounter, use_cache=True)[1].n == 1


def test_rollback_without_backend_is_a_no_op(sess):
    configure_cache(None)
    S.write_row(CCounter(id=1, n=1), sess)
    sess.get(CCounter, 1).n = 99
    sess.flush()
    sess.rollback()
    assert sess.get(CCounter, 1).n == 1


@pytest.mark.asyncio
async def test_async_rollback_after_cached_read_of_uncommitted_data(a_sess):
    await A.write_row(CCounter(id=1, n=1), a_sess)
    b = await a_sess.get(CCounter, 1)
    b.n = 99
    assert (await A.get_row(1, a_sess, CCounter, use_cache=True))[1].n == 99
    await a_sess.rollback()
    assert (await A.get_row(1, a_sess, CCounter, use_cache=True))[1].n == 1


def test_unrebuildable_hit_falls_back_to_a_miss(sess):
    sess.add(CBounded(id=1, n=-5))
    sess.commit()
    assert S.get_row(1, sess, CBounded, use_cache=True)[1].n == -5
    ok, row = S.get_row(1, sess, CBounded, use_cache=True)
    assert ok and row.n == -5
    ok, rows = S.get_rows(sess, CBounded, use_cache=True)
    ok, rows = S.get_rows(sess, CBounded, use_cache=True)
    assert ok and rows[0].n == -5
