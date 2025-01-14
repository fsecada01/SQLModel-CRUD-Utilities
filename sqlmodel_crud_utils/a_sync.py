"""

"""

from typing import Type

from dateutil.parser import parse as date_parse
from dotenv import load_dotenv
from loguru import logger
from sqlalchemy.exc import MultipleResultsFound
from sqlalchemy.orm import lazyload, selectinload
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel.sql.expression import SelectOfScalar

from sqlmodel_crud_utils.utils import get_sql_dialect_import, get_val, is_date

load_dotenv()  # take environment variables from .env.

upsert = get_sql_dialect_import(dialect=get_val("SQL_DIALECT"))


@logger.catch
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


@logger.catch
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


@logger.catch
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


@logger.catch
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


@logger.catch
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


@logger.catch
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
    if stmnt is None:
        stmnt = select(model)
        if kwargs:
            keys = list(kwargs.keys())
            for key in keys:
                if "__lte" in key:
                    model_key = key.replace("__lte", "")
                    val = kwargs.pop(key)
                    if (
                        "date" in key
                        and isinstance(val, str)
                        and is_date(val, fuzzy=False)
                    ):
                        val = date_parse(val)
                    val = (
                        int(val)
                        if isinstance(val, str) and val.isdigit()
                        else val
                    )
                    stmnt = stmnt.where(getattr(model, model_key) < val)
                elif "__gte" in key:
                    model_key = key.replace("__gte", "")
                    val = kwargs.pop(key)
                    if (
                        "date" in key
                        and isinstance(val, str)
                        and is_date(val, fuzzy=False)
                    ):
                        val = date_parse(val)
                    val = (
                        int(val)
                        if isinstance(val, str) and val.isdigit()
                        else val
                    )
                    stmnt = stmnt.where(getattr(model, model_key) > val)
            sort_desc, sort_field = (
                kwargs.pop(x, None) for x in ("sort_desc", "sort_field")
            )
            if sort_field and sort_desc:
                stmnt = stmnt.order_by(getattr(model, sort_field).desc())
            elif sort_field:
                stmnt = stmnt.order_by(getattr(model, sort_field))
            else:
                pass
            if text_field:
                search_val = kwargs.pop(text_field)
                stmnt = stmnt.where(
                    getattr(model, text_field).match(search_val)
                )
            stmnt = stmnt.filter_by(**kwargs)

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

    stmnt = stmnt.offset(page - 1).limit(page_size)
    _result = await session_inst.exec(stmnt)
    results = _result.all()
    success = True if len(results) > 0 else False

    return success, results


@logger.catch
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


@logger.catch
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


@logger.catch
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
        stmnt.returning(model), execution_options={"population_existing": True}
    )

    await session_inst.commit()

    return True, results.all()


@logger.catch
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
