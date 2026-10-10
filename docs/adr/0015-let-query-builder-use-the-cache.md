# 0015. Let the query builder use the read cache

- Status: accepted (amends 0010 and 0012)
- Date: 2026-10-10

## Context
ADR-0012 cached `get_row` and `get_rows` only, and left "integration with the query builder" as a follow-up (issue #38) because the cache and the builder (ADR-0010) were built in parallel. The builder composes statements, so its cache key cannot be a list of keyword filters as it is for `get_rows`. Three things had to be settled: how a builder opts in, what is safe to cache given that a composed statement can reference any table, and how this reuses the invalidation that ADR-0012 already does after every write helper.

## Decision
Reuse the ADR-0012 backend, namespaces, key hashing, row serialization and invalidation. Add no new backend method and no new invalidation path.

### Opt-in
- `QueryBuilder.cached(ttl=None)` and `AsyncQueryBuilder.cached(ttl=None)` return a new immutable builder with caching on; `ttl` is seconds, backend default when `None`, and a negative or non-numeric value raises `ValueError`. Builders are uncached unless `.cached()` is chained, mirroring `use_cache=False` on `get_rows`.
- The terminals `all()`, `first()` and `count()` read from and fill the cache. Without a configured backend (`configure_cache`) `.cached()` is a no-op.

### Cache key
`make_key` is reused with the operation (`qb.all`, `qb.first`, `qb.count`), the model, and the statement the terminal executes, compiled against the session's dialect: its SQL text and its bound parameter values. Where, order by, limit and offset therefore all change the key, and `first()` and `count()` key on their own derived statement, not on the builder's base statement. Bind URL separation is the same as for `get_rows`. The key is the `repr` of the parameter values, so a statement is not cached when it cannot be compiled or when a bound value is anything other than an exact plain scalar type (`None`, `str`, `bytes`, `int`, `float`, `bool`, `Decimal`, date and time types, `UUID`, or an `Enum` with the default `repr`) or a list, tuple, set or dict of them. Subclasses are not trusted: an object with a default or overridden `repr` would collide with a different object that reuses its address or prints the same.

### What is eligible
A builder call is cached only when all of the following hold; otherwise it runs against the database exactly as an uncached builder would, which is the same rule `get_rows` applies:
- No caller `stmnt`. The builder cannot tell whether a caller statement joins other tables or carries options, and `get_rows` already bypasses the cache for a custom `stmnt`. This also covers loader options the caller put on the statement.
- No `selectin()` / `lazy()`. A hit is rebuilt from the model's own columns and cannot carry relationships.
- The composed statement reads only the model's own table. A filter or order expression that pulls in a second table (a join, a subquery, a correlated column) would be invalidated by writes to that table, not by writes to the model, and a stale read could not be ruled out. Statements containing raw `text()` or `literal_column()` are bypassed because the tables they touch cannot be known.
- Only successful, non-empty results are stored, as in ADR-0012: an empty `all()`, a `first()` that finds nothing and a zero `count()` are never cached.

### Results
Stored values are the same JSON-compatible dicts as `get_rows` (`dump_rows`, `dump_row`; a count is `{"count": n}`). A hit rebuilds new session-detached instances with `model_validate`; `exclude=True` fields are round-tripped as for `get_rows`. A cache miss returns live session instances, as before.

### Invalidation
Unchanged. Entries live in the model's table namespace, so every write helper (`write_row`, `insert_data_rows`, `update_row`, `delete_row`, `get_one_or_create`), the three bulk helpers, `transaction()` / `a_transaction()` and `invalidate_cache(model)` already drop them.

## Consequences
- Builder reads can skip the database with one chained call; existing builder code is unaffected.
- The same staleness cases as ADR-0012 apply (writes the library cannot see, a concurrent reader repopulating around a commit, per-process memory). A SQL function or database view that reads another table is not detectable from the statement; use `invalidate_cache` for the tables it reads, or do not cache that query.
- Queries that join or subquery another table are never cached through the builder. That is deliberately conservative; widening it would need multi-namespace entries.
- A hit carries the model's own columns only. A model whose relationships load eagerly by default (for example `lazy="selectin"` in `sa_relationship_kwargs`) returns them empty on a hit, exactly as `get_rows` does; use `selectin()` for relationships (which bypasses the cache) or do not cache that model.
- Two model classes mapped to one table share a namespace; the model is part of the key so their entries do not mix.

## Alternatives considered
- Make the builder cache by default: a silent behaviour change, rejected as in ADR-0012.
- Cache caller `stmnt` builders, keyed on the compiled statement: the key would be correct, but invalidation by model would not be when the statement touches other tables; rejected for consistency with `get_rows`.
- Store an entry under every referenced table's namespace and require all to hit: handles joins, but needs a different lookup and is a parallel mechanism; deferred.
- Let a hit carry relationships by re-attaching to the session: ADR-0012 rejected caching ORM instances.
