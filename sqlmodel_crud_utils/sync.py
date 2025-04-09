""" """

from typing import Type

from dateutil.parser import parse as date_parse
from dotenv import load_dotenv
from loguru import logger
from sqlalchemy.exc import MultipleResultsFound
from sqlalchemy.orm import lazyload, selectinload
from sqlmodel import Session, SQLModel, select
from sqlmodel.sql.expression import SelectOfScalar

from sqlmodel_crud_utils.utils import get_sql_dialect_import, get_val, is_date

load_dotenv()  # take environment variables from .env.

upsert = get_sql_dialect_import(dialect=get_val("SQL_DIALECT"))


@logger.catch
def get_result_from_query(query: SelectOfScalar, session: Session):
    """
    Processes an SQLModel query object and returns a singular result from the
    return payload. If more than one row is returned, then only the first row is
    returned. If no rows are available, then a null value is returned.

    :param query: SelectOfScalar
    :param session: Session

    :return: Row
    """
    results = session.exec(query)
    try:
        results = results.one_or_none()
    except MultipleResultsFound:
        results = session.exec(query)
        results = results.first()

    return results


@logger.catch
def get_one_or_create(
    session_inst: Session,
    model: type[SQLModel],
    create_method_kwargs: dict = None,
    selectin: bool = False,
    select_in_key: str | None = None,
    **kwargs,
):
    """
    This function either returns an existing data row from the database or
    creates a new instance and saves it to the DB.

    :param session_inst: Session
    :param model: SQLModel ORM
    :param create_method_kwargs: dict
    :param selectin: bool
    :param select_in_key: str | None
    :param kwargs: keyword args
    :return: Tuple[Row, bool]
    """

    def _get_entry(sqlmodel, **key_args):
        stmnt = select(sqlmodel).filter_by(**key_args)
        results = get_result_from_query(query=stmnt, session=session_inst)

        if results:
            if selectin and select_in_key:
                stmnt = stmnt.options(
                    selectinload(getattr(sqlmodel, select_in_key))
                )
                results = get_result_from_query(
                    query=stmnt, session=session_inst
                )
            return results, True
        else:
            return results, False

    results, exists = _get_entry(model, **kwargs)
    if results:
        return results, exists
    else:
        kwargs.update(create_method_kwargs or {})
        created = model()
        [setattr(created, k, v) for k, v in kwargs.items()]
        session_inst.add(created)
        session_inst.commit()
        return created, False


@logger.catch
def write_row(data_row: Type[SQLModel], session_inst: Session):
    """
    Writes a new instance of an SQLModel ORM model to the database, with an
    exception catch that rolls back the session in the event of failure.

    :param data_row: Type[SQLModel]
    :param session_inst: Session
    :return: Tuple[bool, ScalarResult]
    """
    try:
        session_inst.add(data_row)
        session_inst.commit()

        return True, data_row
    except Exception as e:
        session_inst.rollback()
        logger.error(
            f"Writing data row to table failed. See error message: "
            f"{type(e), e, e.args}"
        )

        return False, None


@logger.catch
def insert_data_rows(data_rows, session_inst: Session):
    """

    :param data_rows:
    :param session_inst:
    :return:
    """
    try:
        session_inst.add_all(data_rows)
        session_inst.commit()

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

        session_inst.rollback()
        processed_rows, failed_rows = [], []
        for row in data_rows:
            success, processed_row = write_row(row, session_inst=session_inst)
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
def get_row(
    id_str: str or int,
    session_inst: Session,
    model: type[SQLModel],
    selectin: bool = False,
    lazy: bool = False,
    lazy_load_keys: list[str] | None = None,
    select_in_keys: list[str] | None = None,
    pk_field: str = "id",
):
    """

    :param id_str:
    :param session_inst:
    :param model:
    :param selectin:
    :param lazy:
    :param lazy_load_keys:
    :param select_in_keys:
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
    results = session_inst.exec(stmnt)

    row = results.one_or_none()

    if not row:
        success = False
    else:
        success = True

    return success, row


@logger.catch
def get_rows(
    session_inst: Session,
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
                    stmnt = stmnt.where(getattr(model, model_key) <= val)
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
                    stmnt = stmnt.where(getattr(model, model_key) >= val)
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
    _result = session_inst.exec(stmnt)
    results = _result.all()
    success = True if len(results) > 0 else False

    return success, results


@logger.catch
def get_rows_within_id_list(
    id_str_list: list[str | int],
    session_inst: Session,
    model: type[SQLModel],
    pk_field: str = "id",
):
    """
    Retrieves rows from the database whose primary key is within the provided
    list.

    :param id_str_list: List of primary key values to fetch.
    :param session_inst: SQLAlchemy Session instance.
    :param model: SQLModel class representing the table.
    :param pk_field: Name of the primary key field (default: "id").
    :return: Tuple[bool, list[SQLModel]]: A tuple containing a success flag
             (True if rows were found, False otherwise) and a list of the
             found model instances.
    """
    if not id_str_list:  # Handle empty input list
        return False, []

    stmnt = select(model).where(getattr(model, pk_field).in_(id_str_list))
    results = session_inst.exec(stmnt).all()  # Fetch all results into a list

    success = len(results) > 0  # Success is true only if results were found

    return success, results


@logger.catch
def delete_row(
    id_str: str or int,
    session_inst: Session,
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
    results = session_inst.exec(stmnt)

    row = results.one_or_none()

    if not row:
        pass
    else:
        try:
            session_inst.delete(row)
            session_inst.commit()
            success = True
        except Exception as e:
            logger.error(
                f"Failed to delete data row. Please see error messages here: "
                f"{type(e), e, e.args}"
            )
            session_inst.rollback()

    return success


@logger.catch
def bulk_upsert_mappings(
    payload: list,
    session_inst: Session,
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
    session_inst.exec(stmnt)

    results = session_inst.scalars(
        stmnt.returning(model), execution_options={"populate_existing": True}
    )

    session_inst.commit()

    return True, results.all()


@logger.catch
def update_row(
    id_str: int | str,
    data: dict,
    session_inst: Session,
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
    results = session_inst.exec(stmnt)

    row = results.one_or_none()

    if row:
        [setattr(row, k, v) for k, v in data.items()]
        try:
            session_inst.add(row)
            session_inst.commit()
            success = True
        except Exception as e:
            session_inst.rollback()
            logger.error(
                f"Updating the data row failed. See error messages: "
                f"{type(e), e, e.args}"
            )
        return success, row
    else:
        return success, None
