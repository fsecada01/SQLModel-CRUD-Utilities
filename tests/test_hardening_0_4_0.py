"""
Pre-release hardening found by the downstream run (ADR-0018).

* ``written_models`` tolerates sessions that carry no ``.info`` mapping.
* Mixin timestamps are bound as naive UTC whatever the offset or session
  ``TimeZone``, so a naive ``DateTime`` column never shifts the value.
* ``bulk_upsert_mappings`` rejects payloads whose mappings disagree on keys
  rather than silently dropping the extra ones.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlmodel import Field, Session, SQLModel

from sqlmodel_crud_utils import a_sync, sync
from sqlmodel_crud_utils.cache import (
    a_invalidate_written,
    configure_cache,
    invalidate_written,
    written_models,
)
from sqlmodel_crud_utils.mixins import AuditMixin, SoftDeleteMixin, UTCDateTime

from .models import MockModel


class Stamped(AuditMixin, SoftDeleteMixin, SQLModel, table=True):
    __tablename__ = "hardening_stamped"

    id: int | None = Field(default=None, primary_key=True)
    name: str = "x"


@pytest.fixture(autouse=True)
def _no_cache():
    configure_cache(None)
    yield
    configure_cache(None)


@pytest.fixture
def engine(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'h.sqlite'}")
    SQLModel.metadata.create_all(eng)
    return eng


class InfoLessSession:
    """A duck-typed test double: no ``info``, no ``sync_session``."""


class TestWrittenModelsWithoutInfo:
    def test_written_models_returns_the_given_models(self):
        assert written_models(InfoLessSession(), MockModel) == {MockModel}

    def test_invalidate_written_does_not_raise(self):
        invalidate_written(InfoLessSession(), MockModel)

    def test_a_invalidate_written_does_not_raise(self):
        asyncio.run(a_invalidate_written(InfoLessSession(), MockModel))


PLUS_FIVE = timezone(timedelta(hours=5))


class TestUTCDateTime:
    def test_aware_value_is_bound_as_naive_utc(self):
        value = datetime(2026, 1, 1, 12, 0, tzinfo=PLUS_FIVE)
        bound = UTCDateTime().process_bind_param(value, None)
        assert bound == datetime(2026, 1, 1, 7, 0)
        assert bound.tzinfo is None

    def test_naive_value_is_left_alone(self):
        value = datetime(2026, 1, 1, 12, 0)
        assert UTCDateTime().process_bind_param(value, None) == value

    def test_none_passes_through(self):
        assert UTCDateTime().process_bind_param(None, None) is None

    def test_mixin_columns_use_the_type(self):
        table = Stamped.__table__
        for name in ("created_at", "updated_at", "deleted_at"):
            assert isinstance(table.c[name].type, UTCDateTime), name

    def test_orm_round_trip_stores_utc(self, engine):
        value = datetime(2026, 1, 1, 12, 0, tzinfo=PLUS_FIVE)
        with Session(engine) as session:
            row = Stamped(created_at=value)
            session.add(row)
            session.commit()
            row_id = row.id
        with Session(engine) as session:
            stored = session.get(Stamped, row_id).created_at
        assert stored == datetime(2026, 1, 1, 7, 0)

    def test_bulk_soft_delete_stores_utc(self, engine, monkeypatch):
        value = datetime(2026, 1, 1, 12, 0, tzinfo=PLUS_FIVE)
        monkeypatch.setattr(sync, "soft_delete_timestamp", lambda: value)
        with Session(engine) as session:
            session.add(Stamped(id=1))
            session.commit()
            ok, count = sync.delete_rows_within_id_list(
                [1], session, Stamped, soft=True
            )
            assert ok
        with Session(engine) as session:
            assert session.get(Stamped, 1).deleted_at == datetime(
                2026, 1, 1, 7, 0
            )


class Counter:
    def __init__(self):
        self.upserts = 0

    def __call__(self, conn, cursor, statement, *args):
        if statement.lstrip().upper().startswith("INSERT"):
            self.upserts += 1


class TestUpsertPayloadKeys:
    BASE = {"id": 1, "name": "a", "value": 1, "related_field_id": None}

    def _payloads(self):
        extra = {"id": 2, "name": "b", "value": 2, "related_field_id": None}
        return {
            "extra_key": [self.BASE, {**extra, "stray": 1}],
            "missing_key": [self.BASE, {"id": 2, "name": "b"}],
        }

    @pytest.mark.parametrize("case", ["extra_key", "missing_key"])
    def test_sync_rejects_before_any_statement(self, engine, case):
        counter = Counter()
        event.listen(engine, "before_cursor_execute", counter)
        with Session(engine) as session:
            with pytest.raises(ValueError, match="same keys"):
                sync.bulk_upsert_mappings(
                    self._payloads()[case], session, MockModel
                )
        assert counter.upserts == 0

    @pytest.mark.parametrize("case", ["extra_key", "missing_key"])
    def test_async_rejects(self, tmp_path, case):
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlmodel.ext.asyncio.session import AsyncSession

        async def run():
            eng = create_async_engine(
                f"sqlite+aiosqlite:///{tmp_path / 'ha.sqlite'}"
            )
            async with eng.begin() as conn:
                await conn.run_sync(SQLModel.metadata.create_all)
            async with AsyncSession(eng) as session:
                with pytest.raises(ValueError, match="same keys"):
                    await a_sync.bulk_upsert_mappings(
                        self._payloads()[case], session, MockModel
                    )
            await eng.dispose()

        asyncio.run(run())

    def test_uniform_payload_still_works(self, engine):
        rows = [
            self.BASE,
            {"id": 2, "name": "b", "value": 2, "related_field_id": None},
        ]
        with Session(engine) as session:
            ok, result = sync.bulk_upsert_mappings(rows, session, MockModel)
        assert ok and len(result) == 2

    def test_key_order_does_not_matter(self, engine):
        rows = [
            self.BASE,
            {"related_field_id": None, "value": 2, "name": "b", "id": 2},
        ]
        with Session(engine) as session:
            ok, result = sync.bulk_upsert_mappings(rows, session, MockModel)
        assert ok and len(result) == 2
