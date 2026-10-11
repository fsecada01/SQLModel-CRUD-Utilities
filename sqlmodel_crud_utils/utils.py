import importlib
import logging
import math
import os
from typing import Any, Iterator, Sequence

from dateutil.parser import parse as date_parse
from sqlalchemy import func
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import lazyload, selectinload
from sqlalchemy.sql import operators
from sqlalchemy.sql.elements import ColumnClause, TextClause
from sqlalchemy.sql.selectable import TableClause
from sqlalchemy.sql.visitors import iterate
from sqlmodel import select

try:
    from loguru import logger
except ImportError:
    logger: Any = logging.getLogger("sqlmodel_crud_utils")  # type: ignore[assignment]


def get_val(val: str):
    """
    Quick utility to pull environmental variable values after
    loading dot env. It does one thing: either return a value
    from a string representation of an environmental key or
    a Null value.

    :param val: str
    :return: str | None
    """
    return os.environ.get(val, None)


def get_sql_dialect_import(dialect: str):
    """
    A utility function to dynamically load the correct SQL Dialect from the
    SQLAlchemy package.
    :param dialect: str, e.g. ``postgresql``, ``sqlite`` or ``mysql``.

    :return: func
    :raises ValueError: if ``dialect`` is unset/blank or is not a SQLAlchemy
        dialect that provides ``insert``. The message names the
        ``SQL_DIALECT`` environment variable.
    """
    name = (dialect or "").strip()
    if not name:
        raise ValueError(
            "The SQL_DIALECT environment variable is not set. Set it to a "
            "SQLAlchemy dialect name such as 'postgresql', 'sqlite' or "
            "'mysql' (environment or .env file)."
        )
    try:
        return importlib.import_module(f"sqlalchemy.dialects.{name}").insert  # type: ignore[attr-defined]
    except (ImportError, AttributeError) as exc:
        raise ValueError(
            f"SQL_DIALECT={name!r} is not a SQLAlchemy dialect with insert "
            "support. Use a name such as 'postgresql', 'sqlite' or 'mysql'."
        ) from exc


def is_date(val: str, fuzzy: bool = False):
    """
    A simple utility to check if string is a possible datetime value. Returns
    False if not.

    :param val: str
    :param fuzzy: bool = False
    :return:
        bool
    """
    try:
        date_parse(val, fuzzy=fuzzy)
        return True
    except ValueError:
        return False


def validate_primary_key_field(model: Any, pk_field: str) -> None:
    """
    Ensure ``pk_field`` names a primary-key column of ``model``.

    Bulk helpers filter with ``pk_field IN (...)``; accepting a non-unique
    column would turn a "delete these IDs" call into a wide delete.

    :param model: SQLModel table class.
    :param pk_field: Column name to validate.
    :raises ValueError: If ``pk_field`` is not a primary-key column.
    """
    pk_names = [col.key for col in model.__table__.primary_key.columns]
    if pk_field not in pk_names:
        raise ValueError(
            f"{pk_field!r} is not a primary-key column of "
            f"{model.__name__}; expected one of {pk_names}"
        )


def validate_update_columns(model: Any, data: dict) -> None:
    """
    Ensure ``data`` is a non-empty mapping of existing, non-primary-key
    columns of ``model``.

    :param model: SQLModel table class.
    :param data: Column name to new value mapping.
    :raises ValueError: If ``data`` is empty, names an unknown column, or
        names a primary-key column.
    """
    if not data:
        raise ValueError("data must contain at least one column to update")
    columns = {col.key for col in model.__table__.columns}
    pk_names = {col.key for col in model.__table__.primary_key.columns}
    unknown = sorted(set(data) - columns)
    if unknown:
        raise ValueError(f"Unknown column(s) for {model.__name__}: {unknown}")
    protected = sorted(set(data) & pk_names)
    if protected:
        raise ValueError(
            f"Primary-key column(s) cannot be updated: {protected}"
        )


def chunked(items: Sequence, size: int) -> Iterator[Sequence]:
    """
    Yield successive ``size``-length slices of ``items``.

    Keeps ``IN (...)`` lists under backend bind-parameter limits.

    :param items: Sequence to split.
    :param size: Maximum slice length; must be positive.
    :raises ValueError: If ``size`` is not positive.
    """
    if size < 1:
        raise ValueError("chunk_size must be a positive integer")
    for start in range(0, len(items), size):
        yield items[start : start + size]


_SUFFIX_OPS = {
    "gte": operators.ge,
    "gt": operators.gt,
    "lte": operators.le,
    "lt": operators.lt,
}


def reads_only_table(stmnt: Any, table: Any) -> bool:
    """
    Whether ``stmnt`` reads nothing but ``table``.

    Used to decide if a query can be cached under ``table``'s namespace: a
    statement that pulls in another table (join, subquery, correlated
    column) would not be invalidated by writes to ``table``. Raw ``text()``
    and ``literal_column()`` fragments count as unknown and return False.

    :param stmnt: SQLAlchemy statement or clause.
    :param table: The one allowed ``Table``.
    """
    own = (table.schema, table.name)
    for element in iterate(stmnt):
        if isinstance(element, TableClause):
            if (element.schema, element.name) != own:
                return False
        elif isinstance(element, TextClause):
            return False
        elif isinstance(element, ColumnClause) and element.is_literal:
            return False
    return True


class QueryBuilderBase:
    """
    Pure statement composition shared by ``QueryBuilder`` and
    ``AsyncQueryBuilder`` (ADR-0010).

    Instances are immutable: every chaining method returns a new builder, so
    a partially built query can be reused. A caller-supplied ``stmnt`` is the
    starting point and keeps any loader options it carries; builder clauses
    are added on top of it.

    Terminals read from and fill the cache only after ``cached()`` (ADR-0015).

    :param session_inst: Session used by the subclass terminal methods.
    :param model: SQLModel table class being queried.
    :param stmnt: Optional starting ``select`` statement.
    """

    def __init__(self, session_inst: Any, model: Any, stmnt: Any = None):
        self._session = session_inst
        self._model = model
        self._stmnt = select(model) if stmnt is None else stmnt
        self._loaders: dict[str, str] = {}
        self._custom_stmnt = stmnt is not None
        self._use_cache = False
        self._cache_ttl: float | None = None

    def _derive(self, stmnt: Any, loaders: dict[str, str] | None = None):
        builder = type(self)(self._session, self._model, stmnt)
        builder._loaders = self._loaders if loaders is None else loaders
        builder._custom_stmnt = self._custom_stmnt
        builder._use_cache = self._use_cache
        builder._cache_ttl = self._cache_ttl
        return builder

    def cached(self, ttl: float | None = None):
        """
        Let ``all``, ``first`` and ``count`` use the cache (ADR-0015).

        Needs a backend from ``configure_cache``; without one this is a
        no-op. Calls bypass the cache, like ``get_rows``, when the builder
        was given a ``stmnt``, uses ``selectin`` or ``lazy``, or the
        composed statement reads another table or raw SQL. Only non-empty
        results are stored, and a hit rebuilds session-detached instances.
        Writes made through the library's helpers invalidate the entries.

        :param ttl: Seconds an entry lives; the backend default when None.
        :raises ValueError: If ``ttl`` is negative, NaN or not a number.
        :return: A new builder.
        """
        if ttl is not None and (
            isinstance(ttl, bool)
            or not isinstance(ttl, (int, float))
            or math.isnan(ttl)
            or ttl < 0
        ):
            raise ValueError("ttl must be None or a non-negative number")
        builder = self._derive(self._stmnt)
        builder._use_cache = True
        builder._cache_ttl = ttl
        return builder

    def _cache_eligible(self) -> bool:
        """Whether the terminals may use the cache.

        ``first`` and ``count`` derive from the same base statement, so it
        alone decides (the derived ``count(*)`` is itself a literal column).
        """
        return (
            self._use_cache
            and not self._custom_stmnt
            and not self._loaders
            and reads_only_table(self._stmnt, self._model.__table__)
        )

    def _column(self, name: str):
        if name not in self._model.__table__.columns:
            raise ValueError(
                f"{name!r} is not a column of {self._model.__name__}"
            )
        return getattr(self._model, name)

    @staticmethod
    def _check_bound(value: Any, label: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{label} must be a non-negative integer")
        return value

    def where(self, *clauses: Any, **equals: Any):
        """
        Add AND-ed filters.

        :param clauses: SQLAlchemy boolean expressions such as
            ``Model.value > 5`` or ``or_(...)``.
        :param equals: ``column=value`` equality filters. A trailing
            ``__gte``, ``__gt``, ``__lte``, ``__lt``, ``__like`` (matches
            ``%value%``) or ``__in`` (list, tuple or set) suffix selects the
            operator, as in ``get_rows``. A name that is itself a column is
            always equality. Values are used as given, with no date or
            integer coercion.
        :raises ValueError: If a keyword names an unknown column, has an
            unknown suffix, or ``__in`` is not given a list, tuple or set.
        :return: A new builder.
        """
        stmnt = self._stmnt
        if clauses:
            stmnt = stmnt.where(*clauses)
        for name, value in equals.items():
            stmnt = stmnt.where(self._filter_clause(name, value))
        return self._derive(stmnt)

    def _filter_clause(self, name: str, value: Any):
        if name in self._model.__table__.columns or "__" not in name:
            return self._column(name) == value
        field, suffix = name.rsplit("__", 1)
        column = self._column(field)
        if suffix in _SUFFIX_OPS:
            return _SUFFIX_OPS[suffix](column, value)
        if suffix == "like":
            return column.like(f"%{value}%")
        if suffix == "in":
            if not isinstance(value, (list, tuple, set, frozenset)):
                raise ValueError(f"{name} requires a list, tuple or set")
            return column.in_(list(value))
        raise ValueError(f"Unknown filter suffix {suffix!r} in {name!r}")

    def _relationships(self, names: tuple[str, ...], kind: str):
        known = sa_inspect(self._model).relationships
        for name in names:
            if name not in known:
                raise ValueError(
                    f"{name!r} is not a relationship of {self._model.__name__}"
                )
            if self._loaders.get(name, kind) != kind:
                raise ValueError(
                    f"{name!r} already uses {self._loaders[name]} loading; "
                    f"cannot also use {kind}"
                )
        loaders = {**self._loaders, **dict.fromkeys(names, kind)}
        return [getattr(self._model, name) for name in names], loaders

    def selectin(self, *relationships: str):
        """
        Eager load relationships with ``selectinload``.

        :param relationships: Relationship attribute names.
        :raises ValueError: If a name is not a relationship of the model, or
            was already given the other loader.
        :return: A new builder.
        """
        attrs, loaders = self._relationships(relationships, "selectin")
        return self._derive(
            self._stmnt.options(*(selectinload(a) for a in attrs)), loaders
        )

    def lazy(self, *relationships: str):
        """
        Force ``lazyload`` for relationships, overriding model defaults.

        :param relationships: Relationship attribute names.
        :raises ValueError: If a name is not a relationship of the model, or
            was already given the other loader.
        :return: A new builder.
        """
        attrs, loaders = self._relationships(relationships, "lazy")
        return self._derive(
            self._stmnt.options(*(lazyload(a) for a in attrs)), loaders
        )

    def order_by(self, *columns: Any, desc: bool = False):
        """
        Append ORDER BY terms.

        :param columns: Column names or column expressions.
        :param desc: Sort every given column in descending order.
        :raises ValueError: If a name is not a column of the model, or if
            ``desc`` is set and an expression already carries ``asc()`` or
            ``desc()``.
        :return: A new builder.
        """
        terms = [self._column(c) if isinstance(c, str) else c for c in columns]
        if desc:
            if any(
                getattr(t, "modifier", None)
                in (operators.asc_op, operators.desc_op)
                for t in terms
            ):
                raise ValueError(
                    "desc=True cannot be combined with an expression that "
                    "already has a sort direction"
                )
            terms = [t.desc() for t in terms]
        return self._derive(self._stmnt.order_by(*terms))

    def limit(self, count: int):
        """
        Set the maximum number of rows; the last call wins.

        :param count: Non-negative integer.
        :raises ValueError: If ``count`` is not a non-negative integer.
        :return: A new builder.
        """
        count = self._check_bound(count, "limit")
        return self._derive(self._stmnt.limit(count))

    def offset(self, count: int):
        """
        Set the number of rows to skip; the last call wins.

        :param count: Non-negative integer.
        :raises ValueError: If ``count`` is not a non-negative integer.
        :return: A new builder.
        """
        count = self._check_bound(count, "offset")
        return self._derive(self._stmnt.offset(count))

    def _first_stmnt(self):
        cap = 0 if self._stmnt._limit == 0 else 1
        return self._stmnt.limit(cap)

    def _count_stmnt(self):
        return select(func.count()).select_from(self._stmnt.subquery())
