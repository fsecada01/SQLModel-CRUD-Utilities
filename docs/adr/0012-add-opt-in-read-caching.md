# 0012. Add opt-in read caching with a pluggable backend

- Status: accepted
- Date: 2026-10-09

## Context
ADR-0007 deferred caching because it "needs external dependencies". Three questions had to be settled: what the backend interface is, how cache keys are built, and how writes invalidate entries, including the bulk helpers. ADR-0011 established that the bulk helpers (`bulk_upsert_mappings`, `bulk_update_rows`, `delete_rows_within_id_list`) use Core statements and fire no ORM events, and that change tracking is not a complete change feed. Invalidation therefore cannot listen to ORM events or to change history.

## Decision
This supersedes ADR-0007 for caching only. Build it, opt-in, with no new required dependency.

### Backend interface
- `CacheBackend` is an abstract class with four methods: `get(namespace, key)`, `set(namespace, key, value, ttl)`, `invalidate(namespace)` and `clear()`. Values are JSON-compatible dicts or lists.
- `InMemoryCache` is the default: a thread-safe dict with a per-entry TTL and a maximum entry count (oldest entry evicted first). It is per process.
- `RedisCache` is the optional external backend. It needs the `[cache]` extra (`redis>=5`), imported lazily on construction, so importing the library never requires it. It accepts a ready client or a URL. A namespace is a Redis set of its keys, so `invalidate` deletes exactly those keys without a `SCAN`.
- Nothing is cached until the caller runs `configure_cache(backend)`. Without it every read goes straight to the database and every write skips invalidation work. `configure_cache(None)` turns it off again.
- A backend that does blocking I/O sets `blocking = True`; the async helpers then run its calls in a worker thread. `InMemoryCache` is non-blocking and is called inline.

### What is cached
- Only `get_row` and `get_rows`, and only per call with `use_cache=True` (default `False`). Optional `cache_ttl` overrides the backend default.
- Only successful, non-empty results. A miss (not found, empty page) is never cached.
- Only reads of the model's own columns. Calls with `selectin`/`lazy` loading or a caller-supplied `stmnt` bypass the cache, because relationships cannot be stored without a session and a custom statement has no reliable key.
- Stored values are `model_dump(mode="json")` dicts, with `exclude=True` fields added back so a hit does not rebuild them as defaults. A hit rebuilds new transient (session-detached) model instances with `model_validate`. They are not tracked by the session and are not the same objects a database read would return; to modify a row use `update_row`, which re-reads it. Models whose columns do not round-trip through JSON should not be cached.

### Cache keys
Namespace is the model's table name qualified by schema (`schema.table`). The key is the operation name plus, for `get_row`, the primary key field and value, and for `get_rows`, the page, page size, text field and the sorted `repr` of the filter kwargs, plus the session's bind URL with the password hidden. The bind URL keeps two databases that share a table name apart. Keys are hashed to a fixed-length string.

### Invalidation
Invalidation is per namespace (whole table): any write to a model drops every cached read of that model. This is coarse but cannot serve stale rows and needs no query analysis.
- Done explicitly, after a successful commit, by `write_row`, `insert_data_rows`, `update_row`, `delete_row`, `get_one_or_create` (when it creates) and by all three bulk helpers, `bulk_upsert_mappings`, `bulk_update_rows` and `delete_rows_within_id_list`. A failed or rolled-back write invalidates nothing.
- Models written through ORM cascades (`save-update`, `delete`) or added directly to the session before the helper's commit are invalidated too: an `after_flush` listener, installed by `configure_cache`, records every model a flush touches, and the helper invalidates them all after a successful commit. A rollback discards the record.
- Public `invalidate_cache(model=None)` drops one model's entries, or everything when `model` is `None`. Callers use it after raw SQL, direct `session.add`/`session.delete`, writes from other processes, or database-side cascades, none of which the library can see.
- Every entry also expires after its TTL (default 60 seconds), which bounds staleness for anything missed.

## Consequences
- Stale reads are possible in three cases: writes the library does not see (above), a concurrent reader repopulating between a commit and its invalidation, and an in-memory cache in a multi-process deployment (each process has its own; use `RedisCache` there). The TTL is the backstop.
- Cascades and `ON DELETE` actions that change other tables do not invalidate those tables' namespaces. Cached reads exclude relationships, but a foreign key column changed by a database-side action can go stale until expiry or `invalidate_cache`.
- The cache is global module state, set once at startup; per-session or per-engine backends are not supported.
- Follow-up: integration with the query builder (ADR-0010) is not done here.

## Alternatives considered
- Cache ORM instances directly: they are bound to a session and would leak across sessions.
- Per-row or predicate-aware invalidation: needs query analysis; whole-table is simple and safe.
- Invalidate from change tracking events: ADR-0011 says tracking misses the bulk helpers and is opt-in per model.
- `dogpile.cache` or `aiocache` as a dependency: a new required or heavy optional dependency for a small interface.
- Cache by default: a silent behaviour change for existing callers.
