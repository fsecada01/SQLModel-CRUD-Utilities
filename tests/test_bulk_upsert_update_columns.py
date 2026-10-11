"""
``update_columns`` on ``bulk_upsert_mappings`` (ADR-0016, issue #50).

Real-SQLite tests for the sync and async helpers, plus a compile check of the
generated ``ON CONFLICT`` clause for PostgreSQL. A statement counter proves
that validation errors are raised before the database is touched.
"""

import inspect
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from sqlalchemy import create_engine, event, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import Session, SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

import sqlmodel_crud_utils as scu
from sqlmodel_crud_utils import a_sync, sync
from sqlmodel_crud_utils.cache import InMemoryCache, configure_cache

from .models import MockModel

SEED = [
    {"id": 1, "name": "first", "value": 10, "related_field_id": None},
    {"id": 2, "name": "second", "value": 20, "related_field_id": None},
]
# id 1 conflicts, id 3 is new.
INCOMING = [
    {"id": 1, "name": "renamed", "value": 11, "related_field_id": None},
    {"id": 3, "name": "third", "value": 30, "related_field_id": None},
]


class Counter:
    def __init__(self):
        self.statements = []

    def __call__(self, conn, cursor, statement, *args):
        self.statements.append(statement)

    def upserts(self):
        return [
            s
            for s in self.statements
            if s.lstrip().upper().startswith("INSERT")
        ]


def _state(rows):
    return {r.id: (r.name, r.value) for r in rows}


@pytest.fixture(autouse=True)
def _no_cache():
    configure_cache(None)
    yield
    configure_cache(None)


@pytest.fixture
def engine(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'uc.sqlite'}")
    SQLModel.metadata.create_all(eng)
    with Session(eng) as session:
        sync.bulk_upsert_mappings(SEED, session, MockModel)
    eng.dispose()
    eng = create_engine(f"sqlite:///{tmp_path / 'uc.sqlite'}")
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine):
    counter = Counter()
    event.listen(engine, "before_cursor_execute", counter)
    with Session(engine, expire_on_commit=False) as sess:
        sess.counter = counter
        yield sess


@pytest_asyncio.fixture
async def a_session(tmp_path):
    path = tmp_path / "uc_async.sqlite"
    seed_engine = create_engine(f"sqlite:///{path}")
    SQLModel.metadata.create_all(seed_engine)
    with Session(seed_engine) as s:
        sync.bulk_upsert_mappings(SEED, s, MockModel)
    seed_engine.dispose()
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    counter = Counter()
    event.listen(engine.sync_engine, "before_cursor_execute", counter)
    async with AsyncSession(engine, expire_on_commit=False) as sess:
        sess.counter = counter
        yield sess
    await engine.dispose()


def _persisted(session):
    return _state(session.exec(select(MockModel)).scalars().all())


async def _a_persisted(session):
    return _state((await session.exec(select(MockModel))).scalars().all())


# --- signature -------------------------------------------------------------


def test_update_columns_is_last_keyword_with_none_default():
    params = list(
        inspect.signature(sync.bulk_upsert_mappings).parameters.values()
    )
    assert [p.name for p in params] == [
        "payload",
        "session_inst",
        "model",
        "pk_fields",
        "update_columns",
    ]
    assert params[-1].default is None


def test_signatures_match_between_sync_and_async():
    s = inspect.signature(sync.bulk_upsert_mappings).parameters
    a = inspect.signature(a_sync.bulk_upsert_mappings).parameters
    assert list(s) == list(a)
    assert s["update_columns"].default is a["update_columns"].default is None


# --- sync behaviour --------------------------------------------------------


def test_sync_conflict_updates_only_listed_columns(session):
    ok, rows = sync.bulk_upsert_mappings(
        INCOMING, session, MockModel, update_columns=["value"]
    )
    assert ok is True
    # The existing row keeps its name; only value changed. RETURNING agrees.
    assert _state(rows) == {1: ("first", 11), 3: ("third", 30)}
    assert _persisted(session) == {
        1: ("first", 11),
        2: ("second", 20),
        3: ("third", 30),
    }


def test_sync_insert_path_writes_every_provided_column(session):
    ok, rows = sync.bulk_upsert_mappings(
        [{"id": 7, "name": "brand-new", "value": 70}],
        session,
        MockModel,
        update_columns=["value"],
    )
    assert ok is True
    assert _state(rows) == {7: ("brand-new", 70)}
    assert _persisted(session)[7] == ("brand-new", 70)


def test_sync_multiple_update_columns_and_multiple_rows(session):
    payload = [
        {"id": 1, "name": "a", "value": 100, "related_field_id": None},
        {"id": 2, "name": "b", "value": 200, "related_field_id": None},
        {"id": 4, "name": "d", "value": 400, "related_field_id": None},
    ]
    ok, rows = sync.bulk_upsert_mappings(
        payload, session, MockModel, update_columns=["name", "value"]
    )
    assert ok is True
    assert len(rows) == 3
    assert _persisted(session) == {
        1: ("a", 100),
        2: ("b", 200),
        4: ("d", 400),
    }


def test_sync_none_matches_omitting_the_argument(session):
    ok, rows = sync.bulk_upsert_mappings(
        INCOMING, session, MockModel, update_columns=None
    )
    assert ok is True
    assert _persisted(session) == {
        1: ("renamed", 11),
        2: ("second", 20),
        3: ("third", 30),
    }


def test_sync_duplicates_in_update_columns_are_ignored(session):
    ok, _ = sync.bulk_upsert_mappings(
        INCOMING, session, MockModel, update_columns=["value", "value"]
    )
    assert ok is True
    assert _persisted(session)[1] == ("first", 11)


def test_sync_accepts_any_non_string_sequence(session):
    ok, _ = sync.bulk_upsert_mappings(
        INCOMING, session, MockModel, update_columns=("value",)
    )
    assert ok is True
    assert _persisted(session)[1] == ("first", 11)


@pytest.mark.parametrize(
    ("columns", "match"),
    [
        (["nope"], "nope"),
        (["value", "nope", "also_nope"], r"also_nope.*nope|nope.*also_nope"),
        (["Value"], "Value"),
        ([], "update_columns"),
        ((), "update_columns"),
        ("value", "update_columns"),
        (["id"], "id"),
        (["value", "id"], "id"),
    ],
)
def test_sync_validation_errors_before_touching_db(session, columns, match):
    payload = [{"id": 1, "name": "x", "value": 5}]
    before = _persisted(session)
    session.counter.statements.clear()
    with pytest.raises(ValueError, match=match):
        sync.bulk_upsert_mappings(
            payload, session, MockModel, update_columns=columns
        )
    assert session.counter.statements == []
    assert _persisted(session) == before


def test_sync_column_absent_from_payload_is_rejected(session):
    """Otherwise ``excluded.<col>`` would be NULL and wipe the column."""
    with pytest.raises(ValueError, match="value"):
        sync.bulk_upsert_mappings(
            [{"id": 1, "name": "x"}],
            session,
            MockModel,
            update_columns=["value"],
        )
    assert _persisted(session)[1] == ("first", 10)


def test_sync_empty_payload_with_update_columns_is_rejected(session):
    with pytest.raises(ValueError, match="value"):
        sync.bulk_upsert_mappings(
            [], session, MockModel, update_columns=["value"]
        )


def test_sync_error_message_names_model(session):
    with pytest.raises(ValueError, match="MockModel"):
        sync.bulk_upsert_mappings(
            INCOMING, session, MockModel, update_columns=["nope"]
        )


def test_sync_conflict_column_in_update_columns_is_rejected(session):
    with pytest.raises(ValueError, match="Conflict-target"):
        sync.bulk_upsert_mappings(
            INCOMING,
            session,
            MockModel,
            pk_fields=["name"],
            update_columns=["name", "value"],
        )


def test_sync_cache_invalidation_still_fires(session):
    configure_cache(InMemoryCache(default_ttl=60))
    ok, row = scu.get_row(1, session, MockModel, use_cache=True)
    assert row.value == 10
    before = len(session.counter.statements)
    scu.get_row(1, session, MockModel, use_cache=True)
    assert len(session.counter.statements) == before  # served from cache
    sync.bulk_upsert_mappings(
        INCOMING, session, MockModel, update_columns=["value"]
    )
    ok, row = scu.get_row(1, session, MockModel, use_cache=True)
    assert (row.name, row.value) == ("first", 11)


def test_sync_generated_sql_sets_only_listed_columns(session):
    sync.bulk_upsert_mappings(
        INCOMING, session, MockModel, update_columns=["value"]
    )
    (stmt,) = session.counter.upserts()
    set_clause = stmt.split("DO UPDATE SET", 1)[1].split("RETURNING")[0]
    assert set_clause.strip() == "value = excluded.value"


def test_default_generated_sql_sets_every_payload_column(session):
    sync.bulk_upsert_mappings(INCOMING, session, MockModel)
    (stmt,) = session.counter.upserts()
    set_clause = stmt.split("DO UPDATE SET", 1)[1].split("RETURNING")[0]
    for col in ("id", "name", "value", "related_field_id"):
        assert f"{col} = excluded.{col}" in set_clause


@pytest.mark.parametrize("module", [sync, a_sync])
def test_postgresql_statement_sets_only_listed_columns(monkeypatch, module):
    """The clause is dialect-neutral; compile it for PostgreSQL."""
    monkeypatch.setattr(module, "upsert", postgresql.insert)
    captured = {}

    class FakeResult:
        def all(self):
            return []

    def scalars(stmnt, **kwargs):
        captured["stmnt"] = stmnt
        return FakeResult()

    session = MagicMock()
    session.scalars = scalars
    if module is sync:
        module.bulk_upsert_mappings(
            INCOMING,
            session,
            MockModel,
            update_columns=["value"],
        )
    else:
        import asyncio

        async def scalars_async(stmnt, **kwargs):
            captured["stmnt"] = stmnt
            return FakeResult()

        async def commit():
            return None

        session.scalars = scalars_async
        session.commit = commit
        asyncio.run(
            module.bulk_upsert_mappings(
                INCOMING,
                session,
                MockModel,
                update_columns=["value"],
            )
        )
    sql = str(captured["stmnt"].compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT (id) DO UPDATE SET value = excluded.value" in sql
    assert "name = excluded.name" not in sql


# --- async behaviour -------------------------------------------------------


@pytest.mark.asyncio
async def test_async_conflict_updates_only_listed_columns(a_session):
    ok, rows = await a_sync.bulk_upsert_mappings(
        INCOMING, a_session, MockModel, update_columns=["value"]
    )
    assert ok is True
    assert _state(rows) == {1: ("first", 11), 3: ("third", 30)}
    assert await _a_persisted(a_session) == {
        1: ("first", 11),
        2: ("second", 20),
        3: ("third", 30),
    }


@pytest.mark.asyncio
async def test_async_insert_path_writes_every_provided_column(a_session):
    ok, rows = await a_sync.bulk_upsert_mappings(
        [{"id": 7, "name": "brand-new", "value": 70}],
        a_session,
        MockModel,
        update_columns=["value"],
    )
    assert ok is True
    assert (await _a_persisted(a_session))[7] == ("brand-new", 70)


@pytest.mark.asyncio
async def test_async_multiple_columns_and_rows(a_session):
    payload = [
        {"id": 1, "name": "a", "value": 100, "related_field_id": None},
        {"id": 2, "name": "b", "value": 200, "related_field_id": None},
        {"id": 4, "name": "d", "value": 400, "related_field_id": None},
    ]
    ok, rows = await a_sync.bulk_upsert_mappings(
        payload, a_session, MockModel, update_columns=["name", "value"]
    )
    assert ok is True and len(rows) == 3
    assert await _a_persisted(a_session) == {
        1: ("a", 100),
        2: ("b", 200),
        4: ("d", 400),
    }


@pytest.mark.asyncio
async def test_async_none_default_unchanged(a_session):
    ok, _ = await a_sync.bulk_upsert_mappings(
        INCOMING, a_session, MockModel, update_columns=None
    )
    assert ok is True
    assert (await _a_persisted(a_session))[1] == ("renamed", 11)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("columns", "match"),
    [
        (["nope"], "nope"),
        (["Value"], "Value"),
        ([], "update_columns"),
        ("value", "update_columns"),
        (["id"], "id"),
    ],
)
async def test_async_validation_errors_before_touching_db(
    a_session, columns, match
):
    before = await _a_persisted(a_session)
    a_session.counter.statements.clear()
    with pytest.raises(ValueError, match=match):
        await a_sync.bulk_upsert_mappings(
            [{"id": 1, "name": "x", "value": 5}],
            a_session,
            MockModel,
            update_columns=columns,
        )
    assert a_session.counter.statements == []
    assert await _a_persisted(a_session) == before


@pytest.mark.asyncio
async def test_async_column_absent_from_payload_is_rejected(a_session):
    with pytest.raises(ValueError, match="value"):
        await a_sync.bulk_upsert_mappings(
            [{"id": 1, "name": "x"}],
            a_session,
            MockModel,
            update_columns=["value"],
        )
    assert (await _a_persisted(a_session))[1] == ("first", 10)


@pytest.mark.asyncio
async def test_async_conflict_column_in_update_columns_is_rejected(a_session):
    with pytest.raises(ValueError, match="Conflict-target"):
        await a_sync.bulk_upsert_mappings(
            INCOMING,
            a_session,
            MockModel,
            pk_fields=["name"],
            update_columns=["name"],
        )


@pytest.mark.asyncio
async def test_async_cache_invalidation_still_fires(a_session):
    configure_cache(InMemoryCache(default_ttl=60))
    ok, row = await scu.a_get_row(1, a_session, MockModel, use_cache=True)
    assert row.value == 10
    await a_sync.bulk_upsert_mappings(
        INCOMING, a_session, MockModel, update_columns=["value"]
    )
    ok, row = await scu.a_get_row(1, a_session, MockModel, use_cache=True)
    assert (row.name, row.value) == ("first", 11)
