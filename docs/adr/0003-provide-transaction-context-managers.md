# 0003. Provide transaction context managers

- Status: accepted
- Date: 2026-02-16

## Context
The v0.1.0 library had limited transaction management. The design aimed to simplify transaction handling and ensure proper rollback.

## Decision
`transactions.py` provides `transaction(session)` and `a_transaction(session)`. Each commits on success, rolls back on error, and preserves the exception chain (see `TransactionError` in [ADR-0002](0002-use-custom-exception-hierarchy.md)). They are optional; existing functions keep their own commit behaviour.

## Consequences
- The design notes no overhead compared with manual commit and rollback.
- Because they are opt-in, callers who skip them get no new guarantees.
