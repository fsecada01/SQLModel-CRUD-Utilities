# 0010. Add an opt-in fluent query builder

- Status: accepted (amended in #37: loader methods and suffix filters; amended by 0015: cache integration)
- Date: 2026-10-09

## Context
ADR-0007 deferred the query builder because it "needs more design". The
v0.2.0 sketch mutated builder state, had no defined interaction with a
caller-supplied `stmnt`, and said nothing about relationship loading. Issue
#23 asks for `where / order_by / limit / offset / all / first / count` built
on the existing helpers. The open questions were how the builder composes
with a caller statement and with relationship loading.

## Decision
This supersedes ADR-0007 for the query builder only. Add
`QueryBuilder(session_inst, model, stmnt=None)` in `sync.py` and
`AsyncQueryBuilder` in `a_sync.py`, both exported from the package root.
Classes rather than `query()` / `a_query()` factory functions, because the
parity guard requires every `a_sync` function to be a coroutine and an
awaited factory would be awkward. Statement composition lives in a shared pure base in
`utils.py`; only execution differs between the two.

- Builders are immutable: every chained call returns a new builder, so a
  partially built query can be reused safely.
- `where(*clauses, **equals)` takes SQLAlchemy expressions and/or
  keyword equality filters, all AND-ed. `order_by(*columns, desc=False)`
  takes column names or expressions and appends. `limit` and `offset` take
  non-negative integers; the last call wins.
  `desc=True` is rejected with `ValueError` for an expression that already
  carries `asc()` or `desc()`.
- Caller `stmnt`: the builder starts from it and adds its clauses on top
  (AND for filters, appended ordering). This differs deliberately from
  `get_rows`, which runs a custom `stmnt` untouched (issue #11), because
  here the caller opted into composition by using the builder.
- Relationship loading (amended for #37): `selectin(*names)` and
  `lazy(*names)` add `selectinload` / `lazyload` options by relationship
  name, validated against the model (`ValueError` otherwise). Loader options
  already on the starting `stmnt` are still preserved by composition.
  `all()` de-duplicates rows, so collection `joinedload` options work.
- Suffix filters (amended for #37): `where(**filters)` accepts the
  `get_rows` suffixes `__gte`, `__gt`, `__lte`, `__lt`, `__like` (wraps the
  value in `%`) and `__in`. A keyword that is itself a column is always
  equality. Unlike `get_rows`, unknown columns or suffixes and a non-list
  `__in` value raise `ValueError` rather than being skipped or guessed, and
  values get no date or integer coercion.
- `get_rows` is left alone: reimplementing it on the builder would risk its
  untouched-`stmnt`, caching and coercion behavior for no user-visible gain.
- Terminals follow the library's `(success, data)` convention: `all()`
  returns `(bool, list)`, `first()` returns `(bool, row | None)` and
  `count()` returns `(bool, int)`; `success` is true when rows exist. Count
  is taken over the composed statement including any limit and offset.
  `first()` returns at most one row and still honors `limit(0)`, giving
  `(False, None)`.
- Caching (amended for #38): `cached(ttl=None)` lets the terminals use the
  ADR-0012 cache; see ADR-0015 for keys, eligibility and invalidation.
- No new dependency and no change to existing functions.

## Consequences
- Callers get a readable alternative to `get_rows` kwargs, including OR
  and comparison filters through expressions.
- Two filter vocabularies now exist (`get_rows` suffix kwargs and builder
  expressions); the builder does not reimplement the suffix syntax.

## Alternatives considered
- Mutable builder as in the v0.2.0 sketch: rejected, reuse bugs.
- Reimplement `get_rows` suffix filters (`__gte`, `__like`): rejected,
  duplicates fragile parsing; expressions cover it. Revisited in #37: a
  strict subset of suffixes was added, without get_rows' coercion.
- Builder methods for `selectinload`/`lazyload`: deferred, then added in #37.
- Keep deferring: rejected, issue #23 accepted into the v0.4.0 epic.
