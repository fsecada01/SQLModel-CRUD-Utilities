# 0009. Make loguru optional and replace requirements files with uv

- Status: accepted
- Date: 2026-02-16

## Context
The source is a PR summary; it lists changes but does not state the motivation.

## Decision
Remove all `@logger.catch` decorators from `a_sync.py`, `sync.py` and `utils.py`. Make `loguru` an optional or dev-only dependency, no longer required at runtime. Delete `core_requirements.in/txt` and `dev_requirements.in/txt` in favour of `uv` dependency groups, update `release.yml` to use `uv sync --group dev` and `uv build`, and bump to 0.2.0.

## Consequences
- `import sqlmodel_crud_utils` must work without `loguru` installed.
- Rationale not recorded in the source.
