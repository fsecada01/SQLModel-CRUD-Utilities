""" """

from dateutil.parser import parse as date_parse
from dotenv import load_dotenv
from sqlalchemy.exc import MultipleResultsFound
from sqlalchemy.orm import lazyload, selectinload
from sqlmodel import SQLModel, delete, select, update
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel.sql.expression import SelectOfScalar

from sqlmodel_crud_utils.cache import (
    a_invalidate_written,
    a_lookup,
    a_store,
    active_backend,
    dump_row,
    dump_rows,
    load_row,
    load_rows,
    make_key,
    namespace_for,
)
from sqlmodel_crud_utils.tracking import history_select
from sqlmodel_crud_utils.utils import (
    QueryBuilderBase,
    chunked,
    get_sql_dialect_import,
    get_val,
    is_date,
    logger,
    validate_primary_key_field,
    validate_update_columns,
)

load_dotenv()  # take environment variables from .env.

upsert = get_sql_dialect_import(dialect=get_val("SQL_DIALECT"))


async def get_result_from_query(query: SelectOfScalar, session: AsyncSession):
    """
    Processes an SQLModel query object and returns a singular result from the
    return payload. If more than one row is returned, then only the first row is
    returned. If no rows are available, then a null value is returned.

    :param query: SelectOfScalar
    :param session: AsyncSession

    :return: Row
    """
    results = await session.exec(query)
    try:
        results = results.one_or_none()
    except MultipleResultsFound:
        results = await session.exec(query)
        results = results.first()

    return results


async def get_one_or_create(
    session_inst: AsyncSession,
    model: type[SQLModel],
    create_method_kwargs: dict | None = None,
    selectin: bool = False,
    select_in_key: str | None = None,
    **kwargs,
):
    """
    This function either returns an existing data row from the database or
    creates a new instance and saves it to the DB.

    :param session_inst: AsyncSession
    :param model: SQLModel ORM
    :param create_method_kwargs: dict
    :param selectin: bool
    :param select_in_key: str | None
    :param kwargs: keyword args
    :return: Tuple[Row, bool]
    """

    async def _get_entry(sqlmodel, **key_args):
        stmnt = select(sqlmodel).filter_by(**key_args)
        results = await get_result_from_query(query=stmnt, session=session_inst)

        if results:
            if selectin and select_in_key:
                stmnt = stmnt.options(
                    selectinload(getattr(sqlmodel, select_in_key))
                )
                results = await get_result_from_query(
                    query=stmnt, session=session_inst
                )
            return results, True
        else:
            return results, False

    results, exists = await _get_entry(model, **kwargs)
    if results:
        return results, exists
    else:
        kwargs.update(create_method_kwargs or {})
        created = model()
        [setattr(created, k, v) for k, v in kwargs.items()]
        session_inst.add(created)
        await session_inst.commit()
        await a_invalidate_written(session_inst, model)
        return created, False


async def write_row(data_row: SQLModel, session_inst: AsyncSession):
    """
    Writes a new instance of an SQLModel ORM model to the database, with an
    exception catch that rolls back the session in the event of failure.

    :param data_row: SQLModel
    :param session_inst: AsyncSession
    :return: Tuple[bool, ScalarResult]
    """
    try:
        session_inst.add(data_row)
        await session_inst.commit()
        await a_invalidate_written(session_inst, type(data_row))

        return True, data_row
    except Exception as e:
        await session_inst.rollback()
        logger.error(
            f"Writing data row to table failed. See error message: "
            f"{type(e), e, e.args}"
        )

        return False, None


async def insert_data_rows(data_rows, session_inst: AsyncSession):
    """

    :param data_rows:
    :param session_inst:
    :return:
    """
    try:
        session_inst.add_all(data_rows)
        await session_inst.commit()
        await a_invalidate_written(session_inst, *{type(r) for r in data_rows})

        return True, data_rows

    except Exception as e:
        logger.error(
            f"Writing data rows to table failed. See error message: "
            f"{type(e), e, e.args}"
        )
        logger.info(
            "Attempting to write individual entries. This can be a "
            "bit taxing, so please consider your payload to the DB"
        )

        await session_inst.rollback()
        processed_rows, failed_rows = [], []
        for row in data_rows:
            success, processed_row = await write_row(
                row, session_inst=session_inst
            )
            if not success:
                failed_rows.append(row)
            else:
                processed_rows.append(row)

        if processed_rows:
            status = True
        else:
            status = (False,)
        return status, {"success": processed_rows, "failed": failed_rows}


async def get_row(
    id_str: str | int,
    session_inst: AsyncSession,
    model: type[SQLModel],
    selectin: bool = False,
    select_in_keys: list[str] | None = None,
    lazy: bool = False,
    lazy_load_keys: list[str] | None = None,
    pk_field: str = "id",
    use_cache: bool = False,
    cache_ttl: float | None = None,
):
    """

    :param id_str:
    :param session_inst:
    :param model:
    :param selectin:
    :param select_in_keys:
    :param lazy:
    :param lazy_load_keys:
    :param pk_field:
    :param use_cache: Read from and fill the cache set by ``configure_cache``
        (ADR-0012). Bypassed with ``selectin`` or ``lazy``.
    :param cache_ttl: Seconds the entry lives; backend default when None.
    :return:
    """
    backend = active_backend(
        use_cache
        and not (selectin and select_in_keys)
        and not (lazy and lazy_load_keys)
    )
    if backend:
        namespace = namespace_for(model)
        cache_key = make_key(
            session_inst, model, "get_row", pk_field=pk_field, id=id_str
        )
        hit = await a_lookup(backend, namespace, cache_key)
        row = load_row(model, hit) if hit is not None else None
        if row is not None:
            return True, row
    stmnt = select(model).where(getattr(model, pk_field) == id_str)
    if selectin and select_in_keys:
        if isinstance(select_in_keys, list) is False:
            select_in_keys = [select_in_keys]

        for key in select_in_keys:
            stmnt = stmnt.options(selectinload(getattr(model, key)))
    if lazy and lazy_load_keys:
        if isinstance(lazy_load_keys, list) is False:
            lazy_load_keys = [lazy_load_keys]
        for key in lazy_load_keys:
            stmnt = stmnt.options(lazyload(getattr(model, key)))
    results = await session_inst.exec(stmnt)

    row = results.one_or_none()

    if not row:
        success = False
    else:
        success = True
        if backend:
            await a_store(
                backend, namespace, cache_key, dump_row(row), cache_ttl
            )

    return success, row


async def get_rows(
    session_inst: AsyncSession,
    model: type[SQLModel],
    selectin: bool = False,
    select_in_keys: list[str] | None = None,
    lazy: bool = False,
    lazy_load_keys: list[str] | None = None,
    page_size: int = 100,
    page: int = 1,
    text_field: str | None = None,
    stmnt: SelectOfScalar | None = None,
    use_cache: bool = False,
    cache_ttl: float | None = None,
    **kwargs,
):
    """
    Retrieve rows for ``model``, building the query from ``kwargs`` or
    running a caller-supplied statement.

    Pagination applies only to statements built internally (``stmnt`` is
    ``None``): ``page`` and ``page_size`` translate to OFFSET and LIMIT. A
    caller-supplied ``stmnt`` is executed exactly as given; the caller owns
    its pagination, so ``page``, ``page_size`` and any filter, sort or
    loading arguments are ignored. Add ``.limit()``/``.offset()`` to the
    statement yourself when you want a bounded result.

    .. versionchanged:: Unreleased
        A custom ``stmnt`` is no longer silently capped at ``page_size``
        rows (issue #11).

    :param session_inst: Active session used to execute the query.
    :param model: SQLModel table class to query.
    :param selectin: Enable ``selectinload`` for ``select_in_keys``.
    :param select_in_keys: Relationship names to eager load via selectin.
    :param lazy: Enable ``lazyload`` for ``lazy_load_keys``.
    :param lazy_load_keys: Relationship names to lazy load.
    :param page_size: Rows per page; ignored when ``stmnt`` is supplied.
    :param page: 1-based page number; ignored when ``stmnt`` is supplied.
    :param text_field: Field matched with a text search from ``kwargs``.
    :param stmnt: Custom statement, executed as-is and never paginated.
    :param use_cache: Read from and fill the cache set by ``configure_cache``
        (ADR-0012). Bypassed with ``stmnt``, ``selectin`` or ``lazy``.
    :param cache_ttl: Seconds the entry lives; backend default when None.
    :param kwargs: Filters and sort options for the built query.
    :return: ``(success, rows)`` where ``success`` is True if rows exist.
    """
    paginate = stmnt is None
    backend = active_backend(
        use_cache
        and stmnt is None
        and not (selectin and select_in_keys)
        and not (lazy and lazy_load_keys)
    )
    if backend:
        namespace = namespace_for(model)
        cache_key = make_key(
            session_inst,
            model,
            "get_rows",
            page=page,
            page_size=page_size,
            text_field=text_field,
            filters=repr(sorted(kwargs.items(), key=lambda kv: kv[0])),
        )
        hit = await a_lookup(backend, namespace, cache_key)
        rows = load_rows(model, hit) if hit is not None else None
        if rows is not None:
            return True, rows
    # kwargs = {k: v for k, v in kwargs.items() if v}
    # Inside get_rows (sync and async versions)

    # ... existing code ...
    if stmnt is None:
        stmnt = select(model)
        if kwargs:
            # Separate special filter keys from exact match keys
            exact_match_kwargs = {}
            special_filters = {}

            keys_to_process = list(kwargs.keys())  # Iterate over a copy

            for key in keys_to_process:
                val = kwargs[key]
                if "__like" in key:
                    model_key = key.replace("__like", "")
                    special_filters[key] = (
                        getattr(model, model_key).like,
                        f"%{val}%",
                    )  # Adapt for like
                elif "__gte" in key:
                    model_key = key.replace("__gte", "")
                    parsed_val = (
                        date_parse(val)
                        if "date" in key
                        and isinstance(val, str)
                        and is_date(val, fuzzy=False)
                        else (
                            int(val)
                            if isinstance(val, str) and val.isdigit()
                            else val
                        )
                    )
                    special_filters[key] = (
                        getattr(model, model_key).__ge__,
                        parsed_val,
                    )
                elif "__lte" in key:
                    model_key = key.replace("__lte", "")
                    parsed_val = (
                        date_parse(val)
                        if "date" in key
                        and isinstance(val, str)
                        and is_date(val, fuzzy=False)
                        else (
                            int(val)
                            if isinstance(val, str) and val.isdigit()
                            else val
                        )
                    )
                    special_filters[key] = (
                        getattr(model, model_key).__le__,
                        parsed_val,
                    )
                elif "__gt" in key:  # Add __gt if needed
                    model_key = key.replace("__gt", "")
                    parsed_val = (
                        date_parse(val)
                        if "date" in key
                        and isinstance(val, str)
                        and is_date(val, fuzzy=False)
                        else (
                            int(val)
                            if isinstance(val, str) and val.isdigit()
                            else val
                        )
                    )
                    special_filters[key] = (
                        getattr(model, model_key).__gt__,
                        parsed_val,
                    )
                elif "__lt" in key:  # Add __lt if needed
                    model_key = key.replace("__lt", "")
                    parsed_val = (
                        date_parse(val)
                        if "date" in key
                        and isinstance(val, str)
                        and is_date(val, fuzzy=False)
                        else (
                            int(val)
                            if isinstance(val, str) and val.isdigit()
                            else val
                        )
                    )
                    special_filters[key] = (
                        getattr(model, model_key).__lt__,
                        parsed_val,
                    )
                elif "__in" in key:  # Add __in if needed
                    model_key = key.replace("__in", "")
                    if isinstance(val, list):
                        special_filters[key] = (
                            getattr(model, model_key).in_,
                            val,
                        )
                    else:
                        logger.warning(
                            f"Value for __in filter '{key}' is not a list, "
                            f"skipping."
                        )
                elif key not in ("sort_desc", "sort_field") and (
                    not text_field or key != text_field
                ):
                    # Collect keys for filter_by, excluding sort/text search
                    # keys
                    exact_match_kwargs[key] = val

            # Apply special filters using filter()
            for _filter_key, (
                filter_method,
                filter_value,
            ) in special_filters.items():
                stmnt = stmnt.filter(filter_method(filter_value))

            # Apply sorting
            sort_desc = kwargs.get("sort_desc")
            sort_field = kwargs.get("sort_field")
            if sort_field:
                sort_attr = getattr(model, sort_field)
                stmnt = stmnt.order_by(
                    sort_attr.desc() if sort_desc else sort_attr
                )

            # Apply text search if applicable (assuming .match() is correct)
            if text_field and text_field in kwargs:
                search_val = kwargs[text_field]
                stmnt = stmnt.where(
                    getattr(model, text_field).match(search_val)
                )
                # Remove from exact_match_kwargs if it ended up there
                exact_match_kwargs.pop(text_field, None)

            # Apply exact matches using filter_by()
            if exact_match_kwargs:
                stmnt = stmnt.filter_by(**exact_match_kwargs)

        # Apply relationship loading options (Check if key is a relationship
        # first - simplified check)
        if selectin and select_in_keys:
            for key in select_in_keys:
                # Basic check: Does the attribute exist and is it likely a
                # relationship?
                # A more robust check might involve inspecting
                # model.__sqlmodel_relationships__
                attr = getattr(model, key, None)
                if (
                    attr is not None
                    and hasattr(attr, "property")
                    and hasattr(attr.property, "mapper")
                ):
                    stmnt = stmnt.options(selectinload(attr))
                else:
                    logger.warning(
                        f"Skipping selectinload for non-relationship "
                        f"attribute '{key}' on model {model.__name__}"
                    )

        if lazy and lazy_load_keys:
            for key in lazy_load_keys:
                attr = getattr(model, key, None)
                if (
                    attr is not None
                    and hasattr(attr, "property")
                    and hasattr(attr.property, "mapper")
                ):
                    stmnt = stmnt.options(lazyload(attr))
                else:
                    logger.warning(
                        f"Skipping lazyload for non-relationship attribute "
                        f"'{key}' on model {model.__name__}"
                    )

    if paginate:
        stmnt = stmnt.offset((page - 1) * page_size).limit(page_size)
    _result = await session_inst.exec(stmnt)
    results = _result.all()
    success = True if len(results) > 0 else False
    if success and backend:
        await a_store(
            backend,
            namespace,
            cache_key,
            dump_rows(results),
            cache_ttl,
        )

    return success, results


async def get_rows_within_id_list(
    id_str_list: list[str | int],
    session_inst: AsyncSession,
    model: type[SQLModel],
    pk_field: str = "id",
):
    """

    :param id_str_list:
    :param session_inst:
    :param model:
    :param pk_field:
    :return:
    """
    stmnt = select(model).where(getattr(model, pk_field).in_(id_str_list))
    results = await session_inst.exec(stmnt)

    if results:
        success = True
    else:
        success = False

    return success, results


async def delete_rows_within_id_list(
    id_str_list: list[str | int],
    session_inst: AsyncSession,
    model: type[SQLModel],
    pk_field: str = "id",
    chunk_size: int = 500,
) -> tuple[bool, int]:
    """
    Deletes every row whose primary key is within the provided list and
    commits once. IDs with no matching row are ignored.

    This is a hard SQL ``DELETE``: it bypasses ``SoftDeleteMixin`` (rows are
    removed, not marked with ``deleted_at``) and any ORM-level hooks. The ID
    list is split into ``chunk_size`` batches to stay under backend
    bind-parameter limits. One ``DELETE ... WHERE pk IN (...)`` statement is
    sent per batch (never per row), so 1,200 IDs at the default size is 3
    statements. All batches share one transaction, so the call is
    all-or-nothing.

    :param id_str_list: List of primary key values to delete.
    :param session_inst: SQLModel AsyncSession instance.
    :param model: SQLModel class representing the table.
    :param pk_field: Primary-key column to match against (default: "id").
    :param chunk_size: Maximum IDs per DELETE statement (default: 500).
    :return: Tuple[bool, int]: ``True`` and the number of rows deleted. The
        count is 0 when nothing matched or the list was empty.
    :raises ValueError: If ``pk_field`` is not a primary-key column of
        ``model`` or ``chunk_size`` is not positive.
    :raises Exception: Any database error, after the transaction has been
        rolled back and the error logged.
    """
    validate_primary_key_field(model, pk_field)
    deleted = 0
    try:
        for chunk in chunked(id_str_list, chunk_size):
            stmnt = delete(model).where(getattr(model, pk_field).in_(chunk))
            result = await session_inst.exec(stmnt)
            deleted += max(result.rowcount, 0)
        await session_inst.commit()
    except Exception as e:
        await session_inst.rollback()
        logger.error(f"Failed to bulk delete rows: {type(e)}, {e}")
        raise

    await a_invalidate_written(session_inst, model)
    return True, deleted


async def bulk_update_rows(
    id_str_list: list[str | int],
    data: dict,
    session_inst: AsyncSession,
    model: type[SQLModel],
    pk_field: str = "id",
    chunk_size: int = 500,
) -> tuple[bool, int]:
    """
    Applies the same column values to every row whose primary key is within
    the provided list and commits once. IDs with no matching row are ignored.

    This is a Core ``UPDATE``: ORM-level hooks and Python-side defaults do
    not run, so ``AuditMixin.updated_at``/``updated_by`` are not refreshed
    unless the caller includes them in ``data`` (column-level ``onupdate``
    defaults, such as ``TimestampMixin.updated_at``, do fire). The ID list is
    split into ``chunk_size`` batches. One ``UPDATE ... WHERE pk IN (...)``
    statement is sent per batch (never per row), and all batches share one
    transaction.

    :param id_str_list: List of primary key values to update.
    :param data: Mapping of column name to the new value for every row. Must
        be non-empty and may not name a primary-key column.
    :param session_inst: SQLModel AsyncSession instance.
    :param model: SQLModel class representing the table.
    :param pk_field: Primary-key column to match against (default: "id").
    :param chunk_size: Maximum IDs per UPDATE statement (default: 500).
    :return: Tuple[bool, int]: ``True`` and the number of rows matched by the
        update. The count is 0 when nothing matched or the list was empty.
    :raises ValueError: If ``pk_field`` is not a primary-key column,
        ``data`` is empty or names an unknown or primary-key column, or
        ``chunk_size`` is not positive.
    :raises Exception: Any database error, after the transaction has been
        rolled back and the error logged.
    """
    validate_primary_key_field(model, pk_field)
    validate_update_columns(model, data)
    updated = 0
    try:
        for chunk in chunked(id_str_list, chunk_size):
            stmnt = (
                update(model)
                .where(getattr(model, pk_field).in_(chunk))
                .values(**data)
            )
            result = await session_inst.exec(stmnt)
            updated += max(result.rowcount, 0)
        await session_inst.commit()
    except Exception as e:
        await session_inst.rollback()
        logger.error(f"Failed to bulk update rows: {type(e)}, {e}")
        raise

    await a_invalidate_written(session_inst, model)
    return True, updated


async def delete_row(
    id_str: str | int,
    session_inst: AsyncSession,
    model: type[SQLModel],
    pk_field: str = "id",
):
    """

    :param id_str:
    :param session_inst:
    :param model:
    :param pk_field:
    :return:
    """
    success = False
    stmnt = select(model).where(getattr(model, pk_field) == id_str)
    results = await session_inst.exec(stmnt)

    row = results.one_or_none()

    if not row:
        pass
    else:
        try:
            await session_inst.delete(row)
            await session_inst.commit()
            await a_invalidate_written(session_inst, model)
            success = True
        except Exception as e:
            logger.error(
                f"Failed to delete data row. Please see error messages here: "
                f"{type(e), e, e.args}"
            )
            await session_inst.rollback()

    return success


async def bulk_upsert_mappings(
    payload: list,
    session_inst: AsyncSession,
    model: type[SQLModel],
    pk_fields: list[str] | None = None,
):
    """
    Insert or update a batch of rows in a single ``INSERT ... ON CONFLICT DO
    UPDATE ... RETURNING`` statement.

    The ``RETURNING`` rows are fully read (``.all()``) before ``commit()``.
    SQLite refuses to commit while a result cursor is still unread
    ("cannot commit transaction - SQL statements in progress"); Postgres
    tolerates it. The upsert is also executed exactly once rather than once
    bare and once more to fetch the rows.

    Returned instances are expired by ``commit()`` when the session uses
    ``expire_on_commit=True`` (the default), so read their attributes while
    the session is open or create the session with ``expire_on_commit=False``.

    :param payload: Row mappings to upsert; the first mapping's keys decide
        which columns are overwritten on conflict.
    :param session_inst: Active session.
    :param model: Table model being upserted.
    :param pk_fields: Conflict-target columns. Defaults to ``["id"]``.
    :return: ``(True, rows)`` where ``rows`` are the upserted model instances.
    """
    if not pk_fields:
        pk_fields = ["id"]
    stmnt = upsert(model).values(payload)
    stmnt = stmnt.on_conflict_do_update(
        index_elements=[getattr(model, x) for x in pk_fields],
        set_={k: getattr(stmnt.excluded, k) for k in payload[0].keys()},
    )
    results = (
        await session_inst.scalars(
            stmnt.returning(model),
            execution_options={"populate_existing": True},
        )
    ).all()

    await session_inst.commit()
    await a_invalidate_written(session_inst, model)

    return True, results


async def update_row(
    id_str: int | str,
    data: dict,
    session_inst: AsyncSession,
    model: type[SQLModel],
    pk_field: str = "id",
):
    """

    :param id_str:
    :param data:
    :param session_inst:
    :param model:
    :param pk_field:
    :return:
    """
    success = False
    stmnt = select(model).where(getattr(model, pk_field) == id_str)
    results = await session_inst.exec(stmnt)

    row = results.one_or_none()

    if row:
        [setattr(row, k, v) for k, v in data.items()]
        try:
            session_inst.add(row)
            await session_inst.commit()
            await a_invalidate_written(session_inst, model)
            success = True
        except Exception as e:
            await session_inst.rollback()
            logger.error(
                f"Updating the data row failed. See error messages: "
                f"{type(e), e, e.args}"
            )
        return success, row
    else:
        return success, None


async def get_change_history(
    session_inst: AsyncSession,
    model: type[SQLModel],
    id_str: int | str,
):
    """
    Return the recorded change history of one row, oldest first.

    Requires ``register_change_tracking()`` and a model inheriting
    ``TrackChangesMixin`` (ADR-0011). Changes made by the bulk helpers are not
    recorded, so they do not appear here.

    :param session_inst: AsyncSession
    :param model: type[SQLModel]
    :param id_str: primary key value of the row; a tuple or list in
        column order for a composite key
    :return: Tuple[bool, list[dict]]
    """
    stmnt = history_select(model, id_str)
    try:
        conn = await session_inst.connection(bind_arguments={"mapper": model})
        result = await conn.execute(stmnt)
        return True, [dict(r) for r in result.mappings().all()]
    except Exception as e:
        logger.error(
            f"Reading change history failed. See error message: "
            f"{type(e), e, e.args}"
        )
        await session_inst.rollback()
        return False, []


class AsyncQueryBuilder(QueryBuilderBase):
    """
    Immutable fluent query builder bound to an ``AsyncSession`` (ADR-0010).

    Chaining methods are synchronous; the terminals ``all``, ``first`` and
    ``count`` are coroutines returning the library's ``(success, data)``
    tuple where ``success`` is True when rows exist.
    """

    async def all(self):
        """
        :return: ``(success, rows)``; ``rows`` is an empty list when nothing
            matched.
        """
        rows = (await self._session.exec(self._stmnt)).unique().all()
        return len(rows) > 0, rows

    async def first(self):
        """
        :return: ``(success, row)``; ``row`` is ``None`` when nothing matched.
        """
        row = (await self._session.exec(self._first_stmnt())).first()
        return row is not None, row

    async def count(self):
        """
        Count rows of the composed statement, honoring limit and offset.

        :return: ``(success, count)`` with ``success`` True when count > 0.
        """
        total = (await self._session.exec(self._count_stmnt())).one()
        return total > 0, total
