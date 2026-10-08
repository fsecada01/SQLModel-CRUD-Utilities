"""
Parity guards between ``sync.py`` and ``a_sync.py``.

The two modules are hand-maintained mirrors: async I/O cannot be shared with
sync I/O, so only pure helpers live in ``utils.py``. These tests make drift
visible in CI instead of in a user's bug report:

* the public surface (names, coroutine-ness, ``__init__`` exports),
* parameter lists (names, order, kinds, defaults), and
* behavior, by running one scenario through both modules on real SQLite.
"""

import inspect

import pytest
import pytest_asyncio
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import Session, SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

import sqlmodel_crud_utils
from sqlmodel_crud_utils import a_sync, sync

from .models import MockModel

# Functions whose parameter lists are known to differ. Strict xfail: when the
# drift is fixed the test XPASSes and fails, forcing this entry's removal.
KNOWN_SIGNATURE_DRIFT = {
    "get_row": (
        "sync.get_row orders (lazy, lazy_load_keys, select_in_keys) while "
        "a_sync.get_row and both get_rows use (select_in_keys, lazy, "
        "lazy_load_keys); positional callers get different behavior."
    ),
}


def _public_functions(module):
    return {
        name: func
        for name, func in vars(module).items()
        if inspect.isfunction(func)
        and func.__module__ == module.__name__
        and not name.startswith("_")
    }


SYNC_FUNCS = _public_functions(sync)
ASYNC_FUNCS = _public_functions(a_sync)


def _shape(func):
    return [
        (p.name, p.kind, p.default)
        for p in inspect.signature(func).parameters.values()
    ]


def test_modules_expose_the_same_public_functions():
    assert set(SYNC_FUNCS) == set(ASYNC_FUNCS)


@pytest.mark.parametrize("name", sorted(ASYNC_FUNCS))
def test_async_module_functions_are_coroutines(name):
    assert inspect.iscoroutinefunction(ASYNC_FUNCS[name])
    assert not inspect.iscoroutinefunction(SYNC_FUNCS[name])


@pytest.mark.parametrize("name", sorted(SYNC_FUNCS))
def test_package_exports_both_variants(name):
    assert getattr(sqlmodel_crud_utils, name) is SYNC_FUNCS[name]
    assert getattr(sqlmodel_crud_utils, f"a_{name}") is ASYNC_FUNCS[name]
    assert name in sqlmodel_crud_utils.__all__
    assert f"a_{name}" in sqlmodel_crud_utils.__all__


def _signature_params():
    for name in sorted(set(SYNC_FUNCS) & set(ASYNC_FUNCS)):
        marks = []
        if name in KNOWN_SIGNATURE_DRIFT:
            marks.append(
                pytest.mark.xfail(
                    strict=True, reason=KNOWN_SIGNATURE_DRIFT[name]
                )
            )
        yield pytest.param(name, marks=marks, id=name)


@pytest.mark.parametrize("name", list(_signature_params()))
def test_sync_and_async_signatures_match(name):
    assert _shape(SYNC_FUNCS[name]) == _shape(ASYNC_FUNCS[name])


# --- Behavior parity on real SQLite -----------------------------------------

SEED = [
    {"id": 1, "name": "alpha", "value": 10},
    {"id": 2, "name": "beta", "value": 20},
    {"id": 3, "name": "gamma", "value": 30},
]


def _tuples(rows):
    return sorted((r.id, r.name, r.value) for r in rows)


@pytest.fixture
def sync_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'parity.sqlite'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as sess:
        yield sess
    engine.dispose()


@pytest_asyncio.fixture
async def async_session(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'parity_async.sqlite'}"
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    async with AsyncSession(engine, expire_on_commit=False) as sess:
        yield sess
    await engine.dispose()


def _run_sync_scenario(session):
    out = {}
    out["insert"] = sync.insert_data_rows(
        [MockModel(**r) for r in SEED], session
    )[0]
    ok, row = sync.get_row(2, session, MockModel)
    out["get_row"] = (ok, (row.id, row.name, row.value))
    ok, rows = sync.get_rows(session, MockModel)
    out["get_rows"] = (ok, _tuples(rows))
    ok, rows = sync.get_rows(session, MockModel, name="alpha")
    out["get_rows_filtered"] = (ok, _tuples(rows))
    ok, rows = sync.get_rows(session, MockModel, page_size=2, page=2)
    out["get_rows_paged"] = (ok, _tuples(rows))
    ok, rows = sync.get_rows_within_id_list([1, 3, 99], session, MockModel)
    out["within_id_list"] = (ok, _tuples(rows))
    out["update_row"] = sync.update_row(1, {"value": 11}, session, MockModel)
    out["update_missing"] = sync.update_row(
        99, {"value": 1}, session, MockModel
    )
    ok, rows = sync.bulk_upsert_mappings(
        [
            {"id": 3, "name": "gamma2", "value": 31},
            {"id": 4, "name": "d", "value": 40},
        ],
        session,
        MockModel,
    )
    out["bulk_upsert"] = (ok, _tuples(rows))
    row, created = sync.get_one_or_create(session, MockModel, name="alpha")
    out["get_one_existing"] = (created, row.id)
    row, created = sync.get_one_or_create(
        session, MockModel, create_method_kwargs={"value": 5}, name="new"
    )
    out["get_one_created"] = (created, (row.name, row.value))
    out["delete_row"] = sync.delete_row(2, session, MockModel)
    out["delete_missing"] = sync.delete_row(99, session, MockModel)
    out["final"] = _tuples(sync.get_rows(session, MockModel)[1])
    return out


async def _run_async_scenario(session):
    out = {}
    out["insert"] = (
        await a_sync.insert_data_rows([MockModel(**r) for r in SEED], session)
    )[0]
    ok, row = await a_sync.get_row(2, session, MockModel)
    out["get_row"] = (ok, (row.id, row.name, row.value))
    ok, rows = await a_sync.get_rows(session, MockModel)
    out["get_rows"] = (ok, _tuples(rows))
    ok, rows = await a_sync.get_rows(session, MockModel, name="alpha")
    out["get_rows_filtered"] = (ok, _tuples(rows))
    ok, rows = await a_sync.get_rows(session, MockModel, page_size=2, page=2)
    out["get_rows_paged"] = (ok, _tuples(rows))
    ok, rows = await a_sync.get_rows_within_id_list(
        [1, 3, 99], session, MockModel
    )
    out["within_id_list"] = (ok, _tuples(rows))
    out["update_row"] = await a_sync.update_row(
        1, {"value": 11}, session, MockModel
    )
    out["update_missing"] = await a_sync.update_row(
        99, {"value": 1}, session, MockModel
    )
    ok, rows = await a_sync.bulk_upsert_mappings(
        [
            {"id": 3, "name": "gamma2", "value": 31},
            {"id": 4, "name": "d", "value": 40},
        ],
        session,
        MockModel,
    )
    out["bulk_upsert"] = (ok, _tuples(rows))
    row, created = await a_sync.get_one_or_create(
        session, MockModel, name="alpha"
    )
    out["get_one_existing"] = (created, row.id)
    row, created = await a_sync.get_one_or_create(
        session, MockModel, create_method_kwargs={"value": 5}, name="new"
    )
    out["get_one_created"] = (created, (row.name, row.value))
    out["delete_row"] = await a_sync.delete_row(2, session, MockModel)
    out["delete_missing"] = await a_sync.delete_row(99, session, MockModel)
    out["final"] = _tuples((await a_sync.get_rows(session, MockModel))[1])
    return out


@pytest.mark.asyncio
async def test_same_scenario_gives_same_results(sync_session, async_session):
    sync_out = _run_sync_scenario(sync_session)
    async_out = await _run_async_scenario(async_session)

    assert sync_out.keys() == async_out.keys()
    for key in sync_out:
        assert sync_out[key] == async_out[key], key
