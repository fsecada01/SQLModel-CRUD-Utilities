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
import json
import threading
import time
from abc import ABC, abstractmethod
from typing import Any

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


class RedisCache(CacheBackend):
    """Redis-backed cache, shared across processes.

    Needs the optional ``cache`` extra (``pip install
    sqlmodel-crud-utilities[cache]``). Pass a ready ``client`` or a ``url``.
    Each namespace keeps a Redis set of its keys so ``invalidate`` deletes
    exactly those keys without scanning.

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
        self._client.set(full, json.dumps(value), ex=max(1, int(ttl)))
        self._client.sadd(self._index(namespace), full)

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
    databases apart.
    """
    sync_session = getattr(session, "sync_session", session)
    try:
        bind = sync_session.get_bind(mapper=model.__mapper__)
        target = bind.engine.url.render_as_string(hide_password=True)
    except Exception:
        target = "unknown"
    raw = repr((op, target, sorted(parts.items(), key=lambda kv: kv[0])))
    return hashlib.sha256(raw.encode()).hexdigest()


def dump_row(row: SQLModel) -> dict:
    """Serialize a row to a JSON-compatible dict."""
    return row.model_dump(mode="json")


def load_row(model: type[SQLModel], data: dict) -> SQLModel:
    """Rebuild a transient (session-detached) instance from a dict."""
    return model.model_validate(data)


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
    """Write an entry; a failing backend is logged and ignored."""
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
