""" """

from typing import Type

from dateutil.parser import parse as date_parse
from dotenv import load_dotenv
from sqlalchemy.exc import MultipleResultsFound
from sqlalchemy.orm import lazyload, selectinload
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel.sql.expression import SelectOfScalar

from sqlmodel_crud_utils.utils import (
    get_sql_dialect_import,
    get_val,
    is_date,
    logger,
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
    create_method_kwargs: dict = None,
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
        return created, False


async def write_row(data_row: Type[SQLModel], session_inst: AsyncSession):
    """
    Writes a new instance of an SQLModel ORM model to the database, with an
    exception catch that rolls back the session in the event of failure.

    :param data_row: Type[SQLModel]
    :param session_inst: AsyncSession
    :return: Tuple[bool, ScalarResult]
    """
    try:
        session_inst.add(data_row)
        await session_inst.commit()

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
    id_str: str or int,
    session_inst: AsyncSession,
    model: type[SQLModel],
    selectin: bool = False,
    select_in_keys: list[str] | None = None,
    lazy: bool = False,
    lazy_load_keys: list[str] | None = None,
    pk_field: str = "id",
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
    :return:
    """
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
    **kwargs,
):
    """

    :param session_inst:
    :param model:
    :param selectin:
    :param select_in_keys:
    :param lazy:
    :param lazy_load_keys:
    :param page_size:
    :param page:
    :param text_field:
    :param stmnt:
    :param kwargs:
    :return:
    """
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

    # Apply pagination
    stmnt = stmnt.offset((page - 1) * page_size).limit(
        page_size
    )  # Corrected offset calculation
    _result = await session_inst.exec(stmnt)
    results = _result.all()
    success = True if len(results) > 0 else False

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


async def delete_row(
    id_str: str or int,
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

    :param payload:
    :param session_inst:
    :param model:
    :param pk_fields:
    :return:
    """
    if not pk_fields:
        pk_fields = ["id"]
    stmnt = upsert(model).values(payload)
    stmnt = stmnt.on_conflict_do_update(
        index_elements=[getattr(model, x) for x in pk_fields],
        set_={k: getattr(stmnt.excluded, k) for k in payload[0].keys()},
    )
    await session_inst.execute(stmnt)

    results = await session_inst.scalars(
        stmnt.returning(model), execution_options={"populate_existing": True}
    )

    await session_inst.commit()

    return True, results.all()


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
