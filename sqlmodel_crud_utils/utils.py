import importlib
import logging
import os
from typing import Any, Iterator, Sequence

from dateutil.parser import parse as date_parse
from sqlalchemy import func
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
    :param dialect: str

    :return: func
    """
    return importlib.import_module(f"sqlalchemy.dialects.{dialect}").insert  # type: ignore[attr-defined]


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


class QueryBuilderBase:
    """
    Pure statement composition shared by ``QueryBuilder`` and
    ``AsyncQueryBuilder`` (ADR-0010).

    Instances are immutable: every chaining method returns a new builder, so
    a partially built query can be reused. A caller-supplied ``stmnt`` is the
    starting point and keeps any loader options it carries; builder clauses
    are added on top of it.

    :param session_inst: Session used by the subclass terminal methods.
    :param model: SQLModel table class being queried.
    :param stmnt: Optional starting ``select`` statement.
    """

    def __init__(self, session_inst: Any, model: Any, stmnt: Any = None):
        self._session = session_inst
        self._model = model
        self._stmnt = select(model) if stmnt is None else stmnt

    def _derive(self, stmnt: Any):
        return type(self)(self._session, self._model, stmnt)

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
        :param equals: ``column=value`` equality filters.
        :raises ValueError: If a keyword names an unknown column.
        :return: A new builder.
        """
        stmnt = self._stmnt
        if clauses:
            stmnt = stmnt.where(*clauses)
        for name, value in equals.items():
            stmnt = stmnt.where(self._column(name) == value)
        return self._derive(stmnt)

    def order_by(self, *columns: Any, desc: bool = False):
        """
        Append ORDER BY terms.

        :param columns: Column names or column expressions.
        :param desc: Sort every given column in descending order.
        :raises ValueError: If a name is not a column of the model.
        :return: A new builder.
        """
        terms = [self._column(c) if isinstance(c, str) else c for c in columns]
        if desc:
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
        return self._stmnt.limit(1)

    def _count_stmnt(self):
        return select(func.count()).select_from(self._stmnt.subquery())
