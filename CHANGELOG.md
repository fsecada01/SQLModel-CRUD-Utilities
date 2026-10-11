# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.0] - 2026-10-10

### Fixed
- Caching hardening (ADR-0012, #36): `RedisCache` index sets now expire,
  and an entry and its index membership are written atomically (Redis 7+
  for `PEXPIRE NX/GT`). A TTL of zero or less stores nothing and fractional
  TTLs are honoured, matching `InMemoryCache`. An async Redis client raises
  `TypeError` instead of silently missing. Cached values no longer pass
  through custom `field_serializer`s, so a hit equals a database read.
  `transaction()` / `a_transaction()` invalidate the written models after
  commit.
- Importing `sync` / `a_sync` with `SQL_DIALECT` unset (or invalid) now raises
  a clear `ValueError` naming `SQL_DIALECT` instead of
  `No module named 'sqlalchemy.dialects.None'` (#41). `a_sync.get_rows` already
  uses `session.exec()` like `sync.get_rows`; a parity test now pins it (#41).

### Added
- Query builder caching (ADR-0015, #38): `QueryBuilder.cached(ttl=None)` /
  `AsyncQueryBuilder.cached(ttl=None)` let `all()`, `first()` and `count()`
  read from and fill the ADR-0012 cache. Keys cover the composed statement
  and its bound values; entries sit in the model's namespace, so every write
  helper, the bulk helpers and `invalidate_cache()` already drop them.
  Builders with a caller `stmnt`, `selectin()` / `lazy()`, a second table or
  raw `text()` in the statement bypass the cache, like `get_rows`. Opt-in;
  uncached builders behave as before.
- Docs recipes for calling the helpers from a Strawberry or Graphene
  GraphQL resolver (mapping `(success, data)` to GraphQL errors) and for
  using Alembic with the mixins, including adding `HISTORY_METADATA` to
  `target_metadata` (ADR-0013, ADR-0014, #39).
- Query builder `selectin()` / `lazy()` loader methods and `get_rows`-style
  suffix filters (`__gte`, `__gt`, `__lte`, `__lt`, `__like`, `__in`) in
  `where()`, sync and async (ADR-0010 amended, #37).
- Fluent query builder: `QueryBuilder` (sync) and `AsyncQueryBuilder`
  (async), exported from the package root, with `where`, `order_by`,
  `limit`, `offset` and the terminals `all`, `first` and `count`. Builders
  are immutable and compose onto an optional caller `stmnt`, keeping its
  loader options. Opt-in and backward compatible; supersedes ADR-0007 for
  this item (ADR-0010, #23).
- Opt-in read caching (ADR-0012, #25): `get_row()` / `get_rows()` accept
  `use_cache=True` and `cache_ttl` (sync and async). Nothing is cached until
  `configure_cache(backend)` is called. Backends: `InMemoryCache` (default)
  and `RedisCache` (new optional `cache` extra), or subclass `CacheBackend`.
  Every write helper, including the bulk helpers, invalidates the written
  model's entries after commit; `invalidate_cache()` covers writes made
  outside the library. Cache hits are new session-detached instances, and
  calls with `stmnt`, `selectin` or `lazy` bypass the cache.
- Opt-in change tracking (ADR-0011, #24): `TrackChangesMixin`,
  `register_change_tracking()`, the `HISTORY_METADATA` / `change_history`
  table and `get_change_history()` / `a_get_change_history()`. Records ORM
  inserts, updates and deletes with old and new values. The bulk helpers use
  Core statements and are not tracked. The history table is not created
  unless you call `HISTORY_METADATA.create_all()`.

### Decisions
- Migration utilities are not built; use Alembic directly (ADR-0013, #26).
- GraphQL support is not built (ADR-0014, #27).

## [0.3.0] - 2026-10-08

### Added
- `delete_rows_within_id_list()` and `bulk_update_rows()` (sync and async,
  `a_` exports): chunked, single-transaction bulk helpers keyed on a
  validated primary-key column (#12).
- `TimestampMixin`: `created_at`/`updated_at` columns built per model with
  `declared_attr` and `server_default` (#10).
- Architecture Decision Records under `docs/adr/` and a `just adr` helper.

### Changed
- `get_row()` (sync) now orders its optional parameters as
  `selectin, select_in_keys, lazy, lazy_load_keys, pk_field`, matching
  `a_get_row()` and both `get_rows()` functions (#19). Behavior change for
  positional callers: previously `lazy` and `lazy_load_keys` came before
  `select_in_keys`. Keyword callers are unaffected.

### Fixed
- `bulk_upsert_mappings()` / `a_bulk_upsert_mappings()` now run a single
  `RETURNING` statement and read rows before committing, fixing SQLite (#13).
- Package URLs in `pyproject.toml` pointed at the wrong repository (#6).
- `get_rows()` / `a_get_rows()` no longer apply `.offset()/.limit()` to a
  caller-supplied `stmnt`, which was silently truncated to `page_size` (100)
  rows (#11). Behavior change: a custom `stmnt` now runs exactly as given and
  the caller owns its pagination; `page`/`page_size` only affect statements
  built internally.

## [0.2.1] - 2026-04-25

### Added
- Documentation site pages `docs/index.html` (landing page),
  `docs/use-cases.html` and `docs/recipes.html`, alongside the regenerated
  API reference.

### Changed
- `README.md` updated for the 0.2.0 features: usage examples, the exceptions,
  transactions and mixins modules, and PyPI, CI and license badges.
- `docs/make.py` now generates the API reference with `pdoc` while
  preserving the custom landing page, use-cases and recipes pages, fixing the
  docs workflow failure caused by the missing script.

### Fixed
- `Repository` and `Bug Tracker` URLs in `pyproject.toml` now point to
  `fsecada01/SQLModel-CRUD-Utilities`; version bumped to 0.2.1.
- Release workflow: the `build`, `create_release` and `publish_pypi` jobs
  were skipped on `v*` tag pushes because they only matched
  `refs/heads/release/*`. They now run on tag pushes and `release/*` branch
  pushes, and the tag name is extracted correctly from either ref type.

## [0.2.0] - 2026-02-16

### Added
- Public API exports in `__init__.py` for all synchronous CRUD functions
- Public API exports in `__init__.py` for all asynchronous CRUD functions with `a_` prefix
- `__version__` attribute set to "0.2.0"
- `__all__` list for explicit public API definition
- Comprehensive module docstring in `__init__.py`
- This CHANGELOG.md file to track all changes

### Changed
- Made `loguru` an optional dependency via `[loguru]` extra in `pyproject.toml`
- Improved type annotations across the codebase for better type checking support

### Fixed
- Fixed type checking errors in `sync.py` and `a_sync.py` modules
- Fixed parameter name inconsistency in `get_row()` function (`lazy_load_keys` was misspelled as `lazy_load_keys` in sync version)
- Fixed return type issues in various CRUD functions
- Fixed relationship loading validation to properly check if attributes are relationships
- Fixed `get_rows_within_id_list()` in async module to properly return results list
- Documentation build errors related to `dateutil` package

### Removed
- `@logger.catch` decorators from all functions to make `loguru` truly optional

## [0.1.0] - 2024-01-XX

### Added
- Initial release of SQLModel CRUD Utilities
- Synchronous CRUD operations in `sync.py`:
  - `get_row()` - Fetch a single row by primary key
  - `get_rows()` - Fetch multiple rows with filtering, sorting, and pagination
  - `get_one_or_create()` - Get existing record or create new one
  - `write_row()` - Insert a single new row
  - `insert_data_rows()` - Insert multiple rows with fallback
  - `update_row()` - Update an existing row
  - `delete_row()` - Delete a row by primary key
  - `get_rows_within_id_list()` - Fetch rows by list of primary keys
  - `bulk_upsert_mappings()` - Bulk insert-or-update operations
  - `get_result_from_query()` - Execute query and get single result
- Asynchronous CRUD operations in `a_sync.py` (mirror of sync functions)
- Utility functions in `utils.py`:
  - SQL dialect detection and import handling
  - Environment variable management
  - Date parsing utilities
  - Logging configuration
- Flexible filtering with comparison operators (`__like`, `__gte`, `__lte`, `__gt`, `__lt`, `__in`)
- Relationship loading support (eager loading with `selectinload`, lazy loading with `lazyload`)
- Pagination support in `get_rows()` functions
- Dialect-specific upsert operations based on `SQL_DIALECT` environment variable
- Error handling with session rollback on exceptions
- Support for Python 3.9+
- Core dependencies: `sqlmodel>=0.0.24`, `python-dateutil>=2.9.0.post0`, `python-dotenv>=1.1.0`
- Comprehensive test suite with `pytest`, `pytest-asyncio`, and `pytest-cov`
- Documentation generation with `pdoc`
- Code quality tools: `black`, `isort`, `ruff`
- Pre-commit hooks configuration

[unreleased]: https://github.com/fsecada01/SQLModel-CRUD-Utilities/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/fsecada01/SQLModel-CRUD-Utilities/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/fsecada01/SQLModel-CRUD-Utilities/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/fsecada01/SQLModel-CRUD-Utilities/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/fsecada01/SQLModel-CRUD-Utilities/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/fsecada01/SQLModel-CRUD-Utilities/releases/tag/v0.1.0
