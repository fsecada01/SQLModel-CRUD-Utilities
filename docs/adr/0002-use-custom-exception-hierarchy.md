# 0002. Use a custom exception hierarchy

- Status: accepted
- Date: 2026-02-16

## Context
The v0.2.0 design wanted better error handling and debugging for users. The CRUD functions otherwise report failures only through `(success, data)` tuples or raw SQLAlchemy errors.

## Decision
`exceptions.py` defines `SQLModelCRUDError` as the base class, with `RecordNotFoundError`, `MultipleRecordsError`, `ValidationError`, `BulkOperationError` and `TransactionError` beneath it, carrying context about the failed operation. Convenience functions create them. Raising is opt-in through a `raise_on_error=False` default so existing callers keep the tuple-return behaviour (see [ADR-0008](0008-keep-v0-2-0-additive-and-backward-compatible.md)).

## Consequences
- Callers can catch one base class or a specific subclass.
- Rationale for the specific class split is not recorded in the source.
