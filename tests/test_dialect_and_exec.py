"""Regression tests for issue #41: dialect config errors and get_rows exec."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import Session, SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from sqlmodel_crud_utils.a_sync import get_rows as async_get_rows
from sqlmodel_crud_utils.sync import get_rows
from sqlmodel_crud_utils.utils import get_sql_dialect_import

from .models import MockModel

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("dialect", [None, "", "   "])
def test_unset_dialect_raises_clear_error(dialect):
    with pytest.raises(ValueError, match="SQL_DIALECT"):
        get_sql_dialect_import(dialect)


def test_unknown_dialect_raises_clear_error():
    with pytest.raises(ValueError, match="not-a-dialect"):
        get_sql_dialect_import("not-a-dialect")


def test_valid_dialect_still_returns_insert():
    assert callable(get_sql_dialect_import("sqlite"))


@pytest.mark.parametrize("module", ["sync", "a_sync"])
def test_import_without_dialect_fails_clearly(module, tmp_path):
    env = {k: v for k, v in os.environ.items() if k != "SQL_DIALECT"}
    env["PYTHONPATH"] = str(REPO_ROOT)
    proc = subprocess.run(
        [sys.executable, "-c", f"import sqlmodel_crud_utils.{module}"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "SQL_DIALECT" in proc.stderr
    assert "sqlalchemy.dialects.None" not in proc.stderr


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 's.sqlite'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as sess:
        sess.add_all([MockModel(id=i, name=f"r{i}", value=i) for i in (1, 2)])
        sess.commit()
        yield sess
    engine.dispose()


@pytest_asyncio.fixture
async def async_session(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'a.sqlite'}")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    async with AsyncSession(engine, expire_on_commit=False) as sess:
        sess.add_all([MockModel(id=i, name=f"r{i}", value=i) for i in (1, 2)])
        await sess.commit()
        yield sess
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_rows_scalar_and_row_parity(session, async_session):
    """Async get_rows returns the same shapes as sync (exec semantics)."""
    for stmnt in (
        None,
        select(MockModel.id),
        select(MockModel.id, MockModel.name),
    ):
        kw = {} if stmnt is None else {"stmnt": stmnt}
        s_ok, s_rows = get_rows(session_inst=session, model=MockModel, **kw)
        a_ok, a_rows = await async_get_rows(
            session_inst=async_session, model=MockModel, **kw
        )
        assert s_ok is a_ok is True
        assert [type(r) for r in s_rows] == [type(r) for r in a_rows]
        assert len(s_rows) == len(a_rows) == 2
    assert isinstance(a_rows[0], tuple) or hasattr(a_rows[0], "_mapping")
