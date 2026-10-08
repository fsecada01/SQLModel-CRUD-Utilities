"""Tests for TimestampMixin and the AuditMixin multi-model baseline."""

import time
from typing import Optional

import pytest
from sqlalchemy import insert, text
from sqlmodel import Field, Session, SQLModel, create_engine, select

from sqlmodel_crud_utils.mixins import AuditMixin, TimestampMixin


@pytest.fixture
def engine(tmp_path):
    """Real file-backed SQLite engine."""
    return create_engine(f"sqlite:///{tmp_path / 'ts.db'}")


def test_audit_mixin_on_two_tables_baseline(engine):
    """AuditMixin on two table=True models creates both tables."""

    class AuditA(AuditMixin, SQLModel, table=True):
        __tablename__ = "ts_audit_a"
        id: Optional[int] = Field(default=None, primary_key=True)

    class AuditB(AuditMixin, SQLModel, table=True):
        __tablename__ = "ts_audit_b"
        id: Optional[int] = Field(default=None, primary_key=True)

    SQLModel.metadata.create_all(engine)
    with engine.connect() as conn:
        names = {
            r[0]
            for r in conn.execute(
                text("select name from sqlite_master where type='table'")
            )
        }
    assert {"ts_audit_a", "ts_audit_b"} <= names


class StampA(TimestampMixin, SQLModel, table=True):
    __tablename__ = "ts_stamp_a"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = "a"


class StampB(TimestampMixin, SQLModel, table=True):
    __tablename__ = "ts_stamp_b"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = "b"


@pytest.fixture
def models(engine):
    """Create both TimestampMixin tables on the SQLite engine."""
    SQLModel.metadata.create_all(engine)
    return StampA, StampB


def test_exported_from_package():
    import sqlmodel_crud_utils

    assert sqlmodel_crud_utils.TimestampMixin is TimestampMixin
    assert "TimestampMixin" in sqlmodel_crud_utils.__all__


def test_two_models_get_distinct_columns(models):
    a, b = models
    assert a.__table__.c.created_at is not b.__table__.c.created_at
    assert a.__table__.c.updated_at is not b.__table__.c.updated_at


def test_raw_insert_populates_timestamps(engine, models):
    a, b = models
    with engine.begin() as conn:
        conn.execute(insert(a.__table__).values(name="x"))
        conn.execute(insert(b.__table__).values(name="y"))
        for t in (a.__table__, b.__table__):
            row = conn.execute(t.select()).one()
            assert row.created_at is not None
            assert row.updated_at is not None


def test_bulk_insert_mappings_populates_timestamps(engine, models):
    a, _ = models
    with Session(engine) as session:
        session.bulk_insert_mappings(a, [{"name": "p"}, {"name": "q"}])
        session.commit()
        rows = session.exec(select(a)).all()
    assert len(rows) == 2
    assert all(r.created_at and r.updated_at for r in rows)


def test_updated_at_changes_on_update(engine, models):
    a, _ = models
    with Session(engine) as session:
        obj = a(name="before")
        session.add(obj)
        session.commit()
        session.refresh(obj)
        first = obj.updated_at
        created = obj.created_at
        time.sleep(1.1)
        obj.name = "after"
        session.add(obj)
        session.commit()
        session.refresh(obj)
        assert obj.updated_at > first
        assert obj.created_at == created
