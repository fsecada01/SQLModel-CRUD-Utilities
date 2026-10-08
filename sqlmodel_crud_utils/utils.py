import importlib
import logging
import os
from typing import Any, Iterator, Sequence

from dateutil.parser import parse as date_parse

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
    return importlib.import_module(f"sqlalchemy.dialects" f".{dialect}").insert  # type: ignore[attr-defined]


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
