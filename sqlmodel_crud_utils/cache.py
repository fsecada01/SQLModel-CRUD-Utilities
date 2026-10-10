"""
Opt-in read caching for ``get_row`` and ``get_rows`` (ADR-0012).

Nothing is cached until ``configure_cache()`` installs a backend, and even
then only calls that pass ``use_cache=True`` read from it. Every library write
helper, including the bulk helpers, drops the written model's entries after a
successful commit. ``invalidate_cache()`` covers writes the library cannot
see (raw SQL, other processes, database-side cascades).

Hits are rebuilt from JSON-compatible dicts as new, session-detached model
instances, so they are not the objects a database read would return.
"""

import asyncio
import hashlib
import inspect
import json
import math
import threading
import time
from abc import ABC, abstractmethod
from typing import Any

from pydantic_core import to_jsonable_python
from sqlalchemy import event
from sqlalchemy.orm import Session as _SASession
from sqlmodel import SQLModel

from sqlmodel_crud_utils.utils import logger

DEFAULT_TTL = 60.0


class CacheBackend(ABC):
    """Storage for cached read results, grouped by namespace.

    Values are JSON-compatible dicts. ``blocking`` backends perform network
    or disk I/O; the async helpers run their calls in a worker thread.
    """

    blocking: bool = False

    @abstractmethod
    def get(self, namespace: str, key: str) -> Any | None:
        """Return the stored value, or ``None`` on a miss or expiry."""

    @abstractmethod
    def set(
        self,
        namespace: str,
        key: str,
        value: Any,
        ttl: float | None = None,
    ) -> None:
        """Store ``value``; ``ttl`` in seconds overrides the default."""

    @abstractmethod
    def invalidate(self, namespace: str) -> None:
        """Drop every entry in ``namespace``."""

    @abstractmethod
    def clear(self) -> None:
        """Drop every entry in every namespace."""


class InMemoryCache(CacheBackend):
    """Thread-safe, per-process cache with TTL and a size cap.

    :param default_ttl: Seconds an entry lives unless ``set`` overrides it.
    :param max_entries: Entry cap across namespaces; the oldest entry is
        evicted first when it is exceeded.
    """

    def __init__(
        self, default_ttl: float = DEFAULT_TTL, max_entries: int = 1024
    ):
        self.default_ttl = default_ttl
        self.max_entries = max_entries
        self._data: dict[tuple[str, str], tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, namespace, key):
        with self._lock:
            item = self._data.get((namespace, key))
            if item is None:
                return None
            expires, value = item
            if expires <= time.monotonic():
                del self._data[(namespace, key)]
                return None
            return json.loads(value)

    def set(self, namespace, key, value, ttl=None):
        ttl = self.default_ttl if ttl is None else ttl
        with self._lock:
            self._data.pop((namespace, key), None)
            self._data[(namespace, key)] = (
                time.monotonic() + ttl,
                json.dumps(value),
            )
            while len(self._data) > self.max_entries:
                del self._data[next(iter(self._data))]

    def invalidate(self, namespace):
        with self._lock:
            for k in [k for k in self._data if k[0] == namespace]:
                del self._data[k]

    def clear(self):
        with self._lock:
            self._data.clear()


def _is_async_client(client: Any) -> bool:
    """Whether ``client`` is an async Redis client (``redis.asyncio``).

    Its commands return awaitables rather than being coroutine functions, so
    the class module is checked too.
    """
    if inspect.iscoroutinefunction(getattr(client, "get", None)):
        return True
    return any(
        c.__module__.startswith("redis.asyncio") for c in type(client).__mro__
    )


class RedisCache(CacheBackend):
    """Redis-backed cache, shared across processes.

    Needs the optional ``cache`` extra (``pip install
    sqlmodel-crud-utilities[cache]``). Pass a ready ``client`` or a ``url``.
    Each namespace keeps a Redis set of its keys so ``invalidate`` deletes
    exactly those keys without scanning. An entry and its index membership
    are written in one transaction, and the index set expires no earlier than
    its latest entry (this needs Redis 7 for ``PEXPIRE`` with ``NX``/``GT``).
    A ``ttl`` of zero or less stores nothing, matching ``InMemoryCache``.
    The client must be synchronous; an async client raises ``TypeError``.

    :param url: Redis URL used when no ``client`` is given.
    :param client: An existing ``redis.Redis`` compatible client.
    :param default_ttl: Seconds an entry lives unless ``set`` overrides it.
    :param prefix: Prefix for every Redis key this backend writes.
    """

    blocking = True

    def __init__(
        self,
        url: str | None = None,
        client: Any = None,
        default_ttl: float = DEFAULT_TTL,
        prefix: str = "scu",
    ):
        if client is None:
            try:
                import redis
            except ImportError as e:
                raise ImportError(
                    "RedisCache needs the 'cache' extra: "
                    "pip install sqlmodel-crud-utilities[cache]"
                ) from e
            client = redis.Redis.from_url(url or "redis://localhost:6379/0")
        if _is_async_client(client):
            raise TypeError(
                "RedisCache needs a synchronous client (redis.Redis), not an "
                "async one; the async helpers already call it in a thread."
            )
        self._client = client
        self.default_ttl = default_ttl
        self._prefix = prefix

    def _key(self, namespace, key):
        return f"{self._prefix}:{namespace}:{key}"

    def _index(self, namespace):
        return f"{self._prefix}:idx:{namespace}"

    def get(self, namespace, key):
        raw = self._client.get(self._key(namespace, key))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode()
        return json.loads(raw)

    def set(self, namespace, key, value, ttl=None):
        ttl = self.default_ttl if ttl is None else ttl
        full = self._key(namespace, key)
        if ttl <= 0:
            self._client.delete(full)
            return
        millis = max(1, math.ceil(ttl * 1000))
        index = self._index(namespace)
        pipe = self._client.pipeline(transaction=True)
        pipe.set(full, json.dumps(value), px=millis)
        pipe.sadd(index, full)
        pipe.pexpire(index, millis, nx=True)
        pipe.pexpire(index, millis, gt=True)
        pipe.execute()

    def invalidate(self, namespace):
        index = self._index(namespace)
        members = [
            m.decode() if isinstance(m, bytes) else m
            for m in self._client.smembers(index)
        ]
        self._client.delete(*members, index)

    def clear(self):
        keys = list(self._client.scan_iter(match=f"{self._prefix}:*"))
        if keys:
            self._client.delete(*keys)


_backend: CacheBackend | None = None


def configure_cache(backend: CacheBackend | None) -> None:
    """Install ``backend`` as the process-wide cache, or ``None`` to disable.

    Call once at startup. Without a backend, ``use_cache=True`` is a no-op.
    """
    global _backend
    _backend = backend
    if backend is not None:
        _install_flush_listeners()


def get_cache() -> CacheBackend | None:
    """Return the configured backend, or ``None`` when caching is off."""
    return _backend


def namespace_for(model: type[SQLModel]) -> str:
    """Return the cache namespace of a table model: ``schema.table``."""
    table = model.__table__
    return f"{table.schema}.{table.name}" if table.schema else table.name


def make_key(session: Any, model: type[SQLModel], op: str, **parts) -> str:
    """Build a fixed-length key from the operation, arguments and database.

    The bind URL (password hidden) keeps same-named tables in different
    databases apart. In-memory SQLite has no distinguishing URL, so the
    engine identity is added for it.
    """
    sync_session = getattr(session, "sync_session", session)
    try:
        bind = sync_session.get_bind(mapper=model.__mapper__)
        url = bind.engine.url
        target = url.render_as_string(hide_password=True)
        if url.get_backend_name() == "sqlite" and url.database in (
            None,
            "",
            ":memory:",
        ):
            target += f"#{id(bind.engine)}"
    except Exception:
        target = "unknown"
    raw = repr((op, target, sorted(parts.items(), key=lambda kv: kv[0])))
    return hashlib.sha256(raw.encode()).hexdigest()


def dump_row(row: SQLModel) -> dict | None:
    """Serialize a row to a JSON-compatible dict, or ``None`` if it cannot be
    (for example non-UTF-8 ``bytes``), in which case it is not cached.

    Fields declared with ``exclude=True`` are added back, otherwise a hit
    would rebuild them as their defaults."""
    try:
        return {
            name: to_jsonable_python(getattr(row, name))
            for name in type(row).model_fields
        }
    except Exception as e:
        logger.warning(f"Row not cacheable: {type(e), e}")
        return None


def dump_rows(rows: list[SQLModel]) -> dict | None:
    """Serialize a result list, or ``None`` if any row cannot be cached."""
    dumped = [dump_row(r) for r in rows]
    return None if None in dumped else {"rows": dumped}


def load_row(model: type[SQLModel], data: dict) -> SQLModel | None:
    """Rebuild a transient (session-detached) instance from a dict.

    A cached entry that no longer validates (for example a stored value that
    violates a ``Field`` constraint the database does not enforce) returns
    ``None`` so the caller treats the hit as a miss.
    """
    try:
        return model.model_validate(data)
    except Exception as e:
        logger.error(f"Cache entry could not be rebuilt: {type(e), e}")
        return None


def load_rows(model: type[SQLModel], data: dict) -> list[SQLModel] | None:
    """Rebuild a cached result list, or ``None`` if any row cannot be."""
    rows = [load_row(model, r) for r in data["rows"]]
    return None if None in rows else rows


def invalidate_cache(model: type[SQLModel] | None = None) -> None:
    """Drop cached reads of ``model``, or everything when ``model`` is None.

    Use after writes the library cannot see: raw SQL, direct
    ``session.add``/``session.delete``, other processes, or database-side
    cascades.
    """
    backend = _backend
    if backend is None:
        return
    try:
        if model is None:
            backend.clear()
        else:
            backend.invalidate(namespace_for(model))
    except Exception as e:
        logger.error(f"Cache invalidation failed: {type(e), e}")


def active_backend(use_cache: bool) -> CacheBackend | None:
    """Return the backend when this call should use the cache."""
    return _backend if use_cache else None


def lookup(backend: CacheBackend, namespace: str, key: str) -> Any | None:
    """Read an entry; a failing backend counts as a miss."""
    try:
        return backend.get(namespace, key)
    except Exception as e:
        logger.error(f"Cache read failed: {type(e), e}")
        return None


def store(
    backend: CacheBackend,
    namespace: str,
    key: str,
    value: Any,
    ttl: float | None,
) -> None:
    """Write an entry; a failing backend is logged and ignored. A ``None``
    value (an uncacheable result) is skipped."""
    if value is None:
        return
    try:
        backend.set(namespace, key, value, ttl)
    except Exception as e:
        logger.error(f"Cache write failed: {type(e), e}")


async def a_call(backend: CacheBackend, func, *args):
    """Run a backend call, in a worker thread when the backend blocks."""
    if backend.blocking:
        return await asyncio.to_thread(func, *args)
    return func(*args)


async def a_lookup(backend: CacheBackend, namespace: str, key: str):
    """Async ``lookup``."""
    return await a_call(backend, lookup, backend, namespace, key)


async def a_store(backend, namespace, key, value, ttl) -> None:
    """Async ``store``."""
    await a_call(backend, store, backend, namespace, key, value, ttl)


async def a_invalidate_cache(model: type[SQLModel] | None = None) -> None:
    """Async form of ``invalidate_cache`` that keeps blocking I/O off-loop."""
    backend = _backend
    if backend is None:
        return
    await a_call(backend, invalidate_cache, model)


_TOUCHED = "sqlmodel_crud_utils.cache.touched"


def _record_flush(session, flush_context) -> None:
    """``after_flush`` listener noting every model the flush wrote.

    ORM cascades (``save-update``, ``delete``) and objects added directly to
    the session reach models the helper was not called with; recording them
    lets the helper invalidate those namespaces too.
    """
    if _backend is None:
        return
    touched = session.info.setdefault(_TOUCHED, set())
    for obj in (*session.new, *session.dirty, *session.deleted):
        touched.add(type(obj))


def _forget_flush(session) -> None:
    """``after_rollback`` listener for a real (database) rollback.

    Reads inside the transaction may have cached the rolled-back state after
    an autoflush, so every model recorded as touched is invalidated before the
    record is cleared. Does nothing when no backend is configured.
    """
    touched = session.info.pop(_TOUCHED, None)
    if touched and _backend is not None:
        for model in touched:
            invalidate_cache(model)


def _install_flush_listeners() -> None:
    """Idempotently attach the flush and rollback listeners to ``Session``."""
    if not event.contains(_SASession, "after_flush", _record_flush):
        event.listen(_SASession, "after_flush", _record_flush)
    if not event.contains(_SASession, "after_rollback", _forget_flush):
        event.listen(_SASession, "after_rollback", _forget_flush)


def written_models(session: Any, *models: type[SQLModel]) -> set:
    """Pop and return the models flushed through ``session`` plus ``models``.

    Call after a successful commit; the record is cleared so it covers
    exactly one commit.
    """
    sync_session = getattr(session, "sync_session", session)
    found = set(sync_session.info.pop(_TOUCHED, ()))
    found.update(models)
    return found


def invalidate_written(session: Any, *models: type[SQLModel]) -> None:
    """Invalidate ``models`` and every model flushed through ``session``."""
    for model in written_models(session, *models):
        invalidate_cache(model)


async def a_invalidate_written(session: Any, *models: type[SQLModel]) -> None:
    """Async ``invalidate_written`` keeping blocking I/O off the loop."""
    for model in written_models(session, *models):
        await a_invalidate_cache(model)
