# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[unreleased]: https://github.com/fsecada01/sqlmodel_crud_utils/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/fsecada01/sqlmodel_crud_utils/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/fsecada01/sqlmodel_crud_utils/releases/tag/v0.1.0
