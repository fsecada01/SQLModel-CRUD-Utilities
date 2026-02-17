import importlib
import logging
import os
from typing import Any

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
