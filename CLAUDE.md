# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`sqlmodel_crud_utilities` (import name `sqlmodel_crud_utils`): a small library of CRUD helpers over SQLModel, published to PyPI. Every operation returns a `(success: bool, data)` tuple instead of raising for the common "not found / failed" cases.

## Commands

Package manager is `uv`; task runner is `just` (the justfile uses `cmd.exe`, so it targets Windows).

```bash
uv sync --group dev                 # install (dev group has pytest, ruff, black, isort, aiosqlite, loguru)
uv run pytest                       # all tests
uv run pytest tests/test_sync_utils.py::test_name   # single test
uv run pytest -k pattern            # by keyword
uv run pytest --cov=sqlmodel_crud_utils
just lint                           # ruff --fix, isort, black, ty check
just check                          # pre-commit run --all-files
uv run docs/make.py                 # regenerate docs/ (pdoc, keeps custom pages); do not use bare `just docs`
```

Line length is 80 (ruff, black, isort all agree). Ruff selects only `E`, `F`, `B`. Pre-commit runs black on everything except `tests/`; do not run `black` over the whole `tests/` directory, it reformats unrelated files. `uv run` can rewrite `uv.lock`; revert it unless you meant to change dependencies.

## Architecture

- `sync.py` and `a_sync.py` are **parallel implementations** of the same public functions (`get_row`, `get_rows`, `write_row`, `update_row`, `delete_row`, `bulk_upsert_mappings`, `bulk_update_rows`, `delete_rows_within_id_list`, ...). Async versions take `AsyncSession`, are coroutines, and are exported from the package root with an `a_` prefix. A change to one almost always needs the matching change to the other, with identical parameter names and order. `tests/test_sync_async_parity.py` enforces matching function sets, coroutine-ness, `__init__` exports and signatures; add new public functions to both modules and to `__init__.py` / `__all__`.
- `utils.py` holds shared helpers used by both: the `logger` fallback, `get_sql_dialect_import`, and the validation/batching helpers for bulk operations (`validate_primary_key_field`, `validate_update_columns`, `chunked`). Put new shared logic here, not in either sync module.
- `exceptions.py` (`SQLModelCRUDError` hierarchy), `transactions.py` (`transaction` / `a_transaction` context managers) and `mixins.py` (`TimestampMixin`, `AuditMixin`, `SoftDeleteMixin`) are the v0.2.0 additions; all are re-exported from `__init__.py`.
- Bulk write helpers use Core `UPDATE`/`DELETE`, so they bypass ORM hooks, Python-side column defaults, and `SoftDeleteMixin`. IDs are chunked (`chunk_size=500`) in one transaction; DB errors are rolled back, logged and re-raised.
- `get_rows` ignores `page`/`page_size` pagination when a caller supplies their own `stmnt`.

### Environment quirks

- `SQL_DIALECT` (e.g. `postgresql`, `sqlite`, `mysql`) must be set, via the environment or a `.env` file loaded with `python-dotenv`. `sync.py` and `a_sync.py` call `get_sql_dialect_import` at import time to pick the dialect's `insert` for upserts. If it is unset or invalid, importing fails with a `ValueError` naming `SQL_DIALECT`. `tests/conftest.py` sets it to `sqlite` for the test session.
- `loguru` is optional; `utils.logger` falls back to the stdlib logger.
- Tests run against SQLite files (`./test_db.sqlite`, sync via `sqlite://`, async via `sqlite+aiosqlite://`); shared fixtures and the mock models live in `tests/conftest.py` and `tests/models.py`.

## Release and branches

- `main` requires signed commits and linear history. There are no required reviews or status checks; the maintainer squash-merges PRs.
- `.github/workflows/release.yml` triggers on pushes to `release/*` branches (and tags); release branches such as `release/v0.2.0` carry version bumps and may be ahead of or diverge from `main`. Check which one has the version you expect before releasing.
- `CHANGELOG.md` has an Unreleased section; add an entry for user-visible changes, and call out any positional-argument or signature break.
- `docs/*.html` is generated (pdoc plus `docs/make.py`); do not hand-edit.

## Decisions (ADRs)

Significant decisions live in `docs/adr/` as short numbered records (see `docs/adr/README.md` for the template and index). Write one when choosing between real alternatives, when the choice is hard to reverse, or when a future reader will ask "why?". Run `just adr "Title"` to create the next one, fill it in, and add its row to the index in `docs/adr/README.md`. Do not edit an accepted ADR; add a new one that supersedes it and update the old status line. Specs, plans and research go in `docs/specs/`, `docs/plans/` and `docs/research/`, not at the repo root.
