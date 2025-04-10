"""
Tests for the sync functions in `sqlmodel_crud_utils`
"""

from unittest.mock import MagicMock, call, patch

from sqlmodel import Session, select  # Keep Session for type hints

from sqlmodel_crud_utils.sync import (
    bulk_upsert_mappings as sync_bulk_upsert_mappings,
)
from sqlmodel_crud_utils.sync import delete_row as sync_delete_row
from sqlmodel_crud_utils.sync import get_one_or_create as sync_get_one_or_create
from sqlmodel_crud_utils.sync import (
    get_result_from_query as sync_get_result_from_query,
)
from sqlmodel_crud_utils.sync import get_row as sync_get_row
from sqlmodel_crud_utils.sync import get_rows as sync_get_rows
from sqlmodel_crud_utils.sync import (
    get_rows_within_id_list as sync_get_rows_within_id_list,
)
from sqlmodel_crud_utils.sync import insert_data_rows as sync_insert_data_rows
from sqlmodel_crud_utils.sync import update_row as sync_update_row
from sqlmodel_crud_utils.sync import write_row as sync_write_row

from .conftest import MockModelFactory, MockRelatedModelFactory
from .models import MockModel

# --- Tests for get_result_from_query ---
# (No changes needed - use real sessions)


def test_sync_get_result_from_query_one_result(sync_session: Session):
    # Arrange: Create a unique item
    instance = MockModelFactory.build()
    sync_session.add(instance)
    sync_session.commit()
    sync_session.refresh(instance)

    # Act: Query for the specific item
    statement = select(MockModel).where(MockModel.id == instance.id)
    result = sync_get_result_from_query(statement, sync_session)

    # Assert: Check if the correct item is returned
    assert result is not None
    assert result.id == instance.id
    assert result.name == instance.name


def test_sync_get_result_from_query_no_result(sync_session: Session):
    # Arrange: Ensure no item exists with a specific ID
    non_existent_id = 99999

    # Act: Query for the non-existent item
    statement = select(MockModel).where(MockModel.id == non_existent_id)
    result = sync_get_result_from_query(statement, sync_session)

    # Assert: Check if None is returned
    assert result is None


def test_sync_get_result_from_query_multiple_results(sync_session: Session):
    # Arrange: Create multiple items with the same name
    common_name = "MultipleSyncTest"
    instance1 = MockModelFactory.build(name=common_name)
    instance2 = MockModelFactory.build(name=common_name)
    sync_session.add_all([instance1, instance2])
    sync_session.commit()
    sync_session.refresh(instance1)
    sync_session.refresh(instance2)

    # Act: Query by the common name
    statement = select(MockModel).where(MockModel.name == common_name)
    result = sync_get_result_from_query(statement, sync_session)

    # Assert: Check if the first item is returned
    assert result is not None
    assert result.name == common_name
    assert result.id in [instance1.id, instance2.id]


# --- Tests for get_one_or_create ---
# (No changes needed - use real sessions)


def test_sync_get_one_or_create_exists(sync_session: Session):
    # Arrange: Create an item
    existing_instance = MockModelFactory.build(name="ExistingSyncGetOrCreate")
    sync_session.add(existing_instance)
    sync_session.commit()
    sync_session.refresh(existing_instance)

    # Act: Call get_one_or_create
    instance, created = sync_get_one_or_create(
        session_inst=sync_session,
        model=MockModel,
        name=existing_instance.name,
    )

    # Assert: Check existing instance is returned
    assert instance is not None
    assert instance.id == existing_instance.id
    assert instance.name == existing_instance.name
    assert created is True


def test_sync_get_one_or_create_exists_with_selectin(sync_session: Session):
    # Arrange: Create related data and a main model instance
    related_instance = MockRelatedModelFactory.build(
        related_name="SyncSelectInTest"
    )
    sync_session.add(related_instance)
    sync_session.commit()
    sync_session.refresh(related_instance)

    main_instance = MockModelFactory.build(
        name="MainSyncSelectIn", related_field_id=related_instance.id
    )
    sync_session.add(main_instance)
    sync_session.commit()
    sync_session.refresh(main_instance)

    # Act: Call get_one_or_create with selectin=True
    instance, created = sync_get_one_or_create(
        session_inst=sync_session,
        model=MockModel,
        selectin=True,
        select_in_key="related_field",
        name=main_instance.name,
    )

    # Assert: Check instance and related field access
    assert instance is not None
    assert instance.id == main_instance.id
    assert created is True
    assert instance.related_field_id == related_instance.id


def test_sync_get_one_or_create_does_not_exist(sync_session: Session):
    # Arrange: Define criteria for a non-existent item
    new_name = "NewSyncGetOrCreate"
    new_value = 789

    # Act: Call get_one_or_create
    instance, created = sync_get_one_or_create(
        session_inst=sync_session,
        model=MockModel,
        create_method_kwargs={"value": new_value},
        name=new_name,
    )

    # Assert: Check new instance is created
    assert instance is not None
    assert instance.id is not None
    assert instance.name == new_name
    assert instance.value == new_value
    assert created is False

    # Assert: Verify it exists in the DB now
    fetched_instance = sync_session.get(MockModel, instance.id)
    assert fetched_instance is not None
    assert fetched_instance.name == new_name


# --- Tests for write_row ---


def test_sync_write_row_success(sync_session: Session):
    # Arrange: Create a new model instance
    data_row = MockModelFactory.build(name="WriteMeSyncSuccess")

    # Act: Write the row
    success, result = sync_write_row(data_row, sync_session)

    # Assert: Check success and returned object
    assert success is True
    assert result == data_row
    assert result.id is not None

    # Assert: Verify it exists in the DB
    fetched_instance = sync_session.get(MockModel, result.id)
    assert fetched_instance is not None
    assert fetched_instance.name == data_row.name


# This test now correctly uses the mock_sync_session fixture
def test_sync_write_row_failure(mock_sync_session: MagicMock):
    # Arrange
    data_row = MockModel(name="FailSyncWrite")
    mock_sync_session.commit.side_effect = Exception("DB Error")

    # Act
    with patch("sqlmodel_crud_utils.sync.logger.error") as mock_logger:
        success, result = sync_write_row(data_row, mock_sync_session)

    # Assert
    assert success is False
    assert result is None
    mock_sync_session.add.assert_called_once_with(data_row)
    mock_sync_session.commit.assert_called_once()
    mock_sync_session.rollback.assert_called_once()
    mock_logger.assert_called_once()


# --- Tests for insert_data_rows ---


def test_sync_insert_data_rows_success(sync_session: Session):
    # Arrange: Create a list of new model instances
    data_rows = MockModelFactory.build_batch(3)
    names_before = {row.name for row in data_rows}

    # Act: Insert the rows
    success, result = sync_insert_data_rows(data_rows, sync_session)

    # Assert: Check success and returned objects
    assert success is True
    assert result == data_rows
    assert all(row.id is not None for row in result)

    # Assert: Verify they exist in the DB
    ids = [row.id for row in result]
    statement = select(MockModel).where(MockModel.id.in_(ids))
    fetched_rows = sync_session.exec(statement).all()
    assert len(fetched_rows) == len(data_rows)
    names_after = {row.name for row in fetched_rows}
    assert names_after == names_before


# This test now correctly uses the mock_sync_session fixture
def test_sync_insert_data_rows_failure_fallback(mock_sync_session: MagicMock):
    # Arrange
    data_rows = [
        MockModel(id=1, name="RowSync1"),
        MockModel(id=2, name="RowSync2"),
    ]
    mock_sync_session.commit.side_effect = [
        Exception("Bulk DB Error"),
        None,  # Success for row 1
        Exception("Single DB Error"),  # Failure for row 2
    ]
    mock_sync_session.rollback.side_effect = [None, None]

    # Act
    with (
        patch("sqlmodel_crud_utils.sync.logger.error") as mock_logger_error,
        patch("sqlmodel_crud_utils.sync.logger.info") as mock_logger_info,
    ):
        success, result = sync_insert_data_rows(data_rows, mock_sync_session)

    # Assert
    assert success is True
    assert len(result["success"]) == 1
    assert result["success"][0].name == "RowSync1"
    assert len(result["failed"]) == 1
    assert result["failed"][0].name == "RowSync2"

    # Check mock calls
    mock_sync_session.add_all.assert_called_once_with(data_rows)
    assert mock_sync_session.commit.call_count == 3
    assert mock_sync_session.rollback.call_count == 2
    assert mock_sync_session.add.call_count == 2
    mock_sync_session.add.assert_has_calls(
        [call(data_rows[0]), call(data_rows[1])], any_order=False
    )
    assert mock_logger_error.call_count == 2
    mock_logger_info.assert_called_once()


# This test now correctly uses the mock_sync_session fixture
def test_sync_insert_data_rows_failure_all_fallback_fail(
    mock_sync_session: MagicMock,
):
    # Arrange
    data_rows = [
        MockModel(id=1, name="RowSync1"),
        MockModel(id=2, name="RowSync2"),
    ]
    mock_sync_session.commit.side_effect = [
        Exception("Bulk DB Error"),
        Exception("Single DB Error 1"),
        Exception("Single DB Error 2"),
    ]
    mock_sync_session.rollback.side_effect = [None, None, None]

    # Act
    with (
        patch("sqlmodel_crud_utils.sync.logger.error") as mock_logger_error,
        patch("sqlmodel_crud_utils.sync.logger.info") as mock_logger_info,
    ):
        success, result = sync_insert_data_rows(data_rows, mock_sync_session)

    # Assert
    assert success == (False,)
    assert len(result["success"]) == 0
    assert len(result["failed"]) == 2
    assert result["failed"] == data_rows

    # Check mock calls
    mock_sync_session.add_all.assert_called_once_with(data_rows)
    assert mock_sync_session.commit.call_count == 3
    assert mock_sync_session.rollback.call_count == 3
    assert mock_sync_session.add.call_count == 2
    mock_sync_session.add.assert_has_calls(
        [call(data_rows[0]), call(data_rows[1])], any_order=False
    )
    assert mock_logger_error.call_count == 3
    mock_logger_info.assert_called_once()


# --- Tests for get_row ---
# (No changes needed - use real sessions)


def test_sync_get_row_found(sync_session: Session):
    # Arrange: Create an item
    instance = MockModelFactory.build(name="GetSyncRowFound")
    sync_session.add(instance)
    sync_session.commit()
    sync_session.refresh(instance)

    # Act: Get the row by ID
    success, row = sync_get_row(
        id_str=instance.id, session_inst=sync_session, model=MockModel
    )

    # Assert: Check success and data
    assert success is True
    assert row is not None
    assert row.id == instance.id
    assert row.name == instance.name


def test_sync_get_row_not_found(sync_session: Session):
    # Arrange: ID that doesn't exist
    non_existent_id = 99998

    # Act: Try to get the row
    success, row = sync_get_row(
        id_str=non_existent_id, session_inst=sync_session, model=MockModel
    )

    # Assert: Check failure
    assert success is False
    assert row is None


def test_sync_get_row_with_options(sync_session: Session):
    # Arrange: Create related and main instances
    related = MockRelatedModelFactory.build(
        related_name="SyncWithOptionsRelated"
    )
    sync_session.add(related)
    sync_session.commit()
    sync_session.refresh(related)

    main = MockModelFactory.build(
        name="SyncWithOptionsMain", related_field_id=related.id
    )
    sync_session.add(main)
    sync_session.commit()
    sync_session.refresh(main)

    # Act: Get the row with options
    success, row = sync_get_row(
        id_str=main.id,
        session_inst=sync_session,
        model=MockModel,
        selectin=True,
        select_in_keys=["related_field"],
    )

    # Assert: Check success and data accessibility
    assert success is True
    assert row is not None
    assert row.id == main.id
    assert row.related_field_id == related.id
    assert row.value == main.value


# --- Tests for get_rows ---
# (No changes needed - use real sessions)


def test_sync_get_rows_basic(sync_session: Session):
    # Arrange: Create some data
    unique_prefix = f"SyncBasic-{MockModelFactory.build().id}"
    instances = MockModelFactory.build_batch(5)
    inst_array = []
    for i, inst in enumerate(instances):
        row = MockModel(
            **inst.model_dump(exclude={"id", "name"}),
            name=f"{unique_prefix}-{i}",
        )
        row.id = None
        inst_array.append(row)
    instances = inst_array
    sync_session.add_all(instances)
    sync_session.commit()

    # Act: Get the first page
    success, rows = sync_get_rows(
        session_inst=sync_session,
        model=MockModel,
        name__like=f"{unique_prefix}-%",
    )

    # Assert: Check success and that some rows are returned
    assert success is True
    assert isinstance(rows, list)
    assert len(rows) == 5


def test_sync_get_rows_pagination(sync_session: Session):
    # Arrange: Create enough data for pagination
    batch_size = 25
    unique_prefix = f"SyncPaginate-{MockModelFactory.build().id}"
    instances = MockModelFactory.build_batch(batch_size)
    inst_array = []
    for i, inst in enumerate(instances):
        row = MockModel(
            **inst.model_dump(exclude={"id", "name"}),
            name=f"{unique_prefix}-{i}",
        )
        row.id = None
        inst_array.append(row)
    instances = inst_array
    sync_session.add_all(instances)
    sync_session.commit()
    for inst in instances:
        sync_session.refresh(inst)

    all_ids_sorted = sorted([inst.id for inst in instances])

    page_size = 10
    page = 2
    offset = (page - 1) * page_size
    expected_ids = all_ids_sorted[offset : offset + page_size]

    # Act: Get a specific page
    success, rows = sync_get_rows(
        session_inst=sync_session,
        model=MockModel,
        page_size=page_size,
        page=page,
        sort_field="id",
        name__like=f"{unique_prefix}-%",
    )

    # Assert: Check success and compare IDs
    assert success is True
    assert len(rows) == len(expected_ids)
    assert [row.id for row in rows] == expected_ids


def test_sync_get_rows_with_filters_and_sort(sync_session: Session):
    # Arrange: Create specific data
    target_name = "SyncFilterTestTarget"
    other_name = "SyncFilterTestOther"
    instances = [
        MockModelFactory.build(name=target_name, value=50),
        MockModelFactory.build(name=target_name, value=150),
        MockModelFactory.build(name=other_name, value=100),
        MockModelFactory.build(name=target_name, value=20),
    ]
    sync_session.add_all(instances)
    sync_session.commit()

    # Act: Get rows with filters and sorting
    with patch("sqlmodel_crud_utils.sync.getattr", side_effect=getattr):
        success, rows = sync_get_rows(
            session_inst=sync_session,
            model=MockModel,
            name=target_name,
            value__gte=50,
            sort_field="value",
            sort_desc=True,
        )

    # Assert: Check success and results
    assert success is True
    assert len(rows) == 2
    assert rows[0].name == target_name
    assert rows[1].name == target_name
    assert rows[0].value == 150
    assert rows[1].value == 50


def test_sync_get_rows_no_results(sync_session: Session):
    # Arrange: Use a filter guaranteed to find nothing
    non_existent_name = "ThisSyncNameDoesNotExistForSure"
    existing = sync_session.exec(
        select(MockModel).where(MockModel.name == non_existent_name)
    ).first()
    assert existing is None

    # Act: Get rows with the filter
    success, rows = sync_get_rows(
        session_inst=sync_session, model=MockModel, name=non_existent_name
    )

    # Assert: Check failure and empty list
    assert success is False
    assert rows == []


# --- Tests for get_rows_within_id_list ---
# (No changes needed - use real sessions)


def test_sync_get_rows_within_id_list_found(sync_session: Session):
    # Arrange: Create some items and get their IDs
    instances = MockModelFactory.build_batch(3)
    sync_session.add_all(instances)
    sync_session.commit()
    ids_to_find = []
    for inst in instances:
        sync_session.refresh(inst)
        ids_to_find.append(inst.id)

    extra_instance = MockModelFactory.build()
    sync_session.add(extra_instance)
    sync_session.commit()

    # Act: Get rows with the list of IDs
    with patch("sqlmodel_crud_utils.sync.getattr", side_effect=getattr):
        success, results = sync_get_rows_within_id_list(
            id_str_list=ids_to_find,
            session_inst=sync_session,
            model=MockModel,
        )

    # Assert: Check success and that the correct rows were found
    assert success is True
    assert len(results) == len(ids_to_find)
    assert {row.id for row in results} == set(ids_to_find)


def test_sync_get_rows_within_id_list_not_found(sync_session: Session):
    # Arrange: List of IDs guaranteed not to exist
    non_existent_ids = [-1, -2, -3]

    # Act: Get rows with the non-existent IDs
    success, results = sync_get_rows_within_id_list(
        id_str_list=non_existent_ids,
        session_inst=sync_session,
        model=MockModel,
    )

    # Assert: Check failure and empty results
    assert success is False
    assert results == []


# --- Tests for delete_row ---


def test_sync_delete_row_success(sync_session: Session):
    # Arrange: Create an item to delete
    instance = MockModelFactory.build(name="SyncToDelete")
    sync_session.add(instance)
    sync_session.commit()
    sync_session.refresh(instance)
    instance_id = instance.id

    # Act: Delete the row
    success = sync_delete_row(
        id_str=instance_id, session_inst=sync_session, model=MockModel
    )

    # Assert: Check success
    assert success is True

    # Assert: Verify it's gone from the DB
    fetched_instance = sync_session.get(MockModel, instance_id)
    assert fetched_instance is None


def test_sync_delete_row_not_found(sync_session: Session):
    # Arrange: ID that doesn't exist
    non_existent_id = 99997

    # Act: Try to delete the non-existent row
    success = sync_delete_row(
        id_str=non_existent_id, session_inst=sync_session, model=MockModel
    )

    # Assert: Check failure
    assert success is False


# This test now correctly uses the mock_sync_session fixture
def test_sync_delete_row_failure(mock_sync_session: MagicMock):
    # Arrange: Mock finding the row but failing on commit
    mock_instance = MockModel(id=1, name="SyncToDeleteFail")
    # Configure mock exec().one_or_none()
    mock_sync_session.exec.return_value.one_or_none.return_value = mock_instance
    mock_sync_session.commit.side_effect = Exception("Delete DB Error")

    # Act
    with patch("sqlmodel_crud_utils.sync.logger.error") as mock_logger:
        success = sync_delete_row(
            id_str=1, session_inst=mock_sync_session, model=MockModel
        )

    # Assert
    assert success is False
    # Check mock calls
    mock_sync_session.exec.assert_called_once()
    mock_sync_session.exec.return_value.one_or_none.assert_called_once()
    mock_sync_session.delete.assert_called_once_with(mock_instance)
    mock_sync_session.commit.assert_called_once()
    mock_sync_session.rollback.assert_called_once()
    mock_logger.assert_called_once()


# --- Tests for bulk_upsert_mappings ---


# This test now correctly uses the mock_sync_session fixture
@patch("sqlmodel_crud_utils.sync.upsert")
def test_sync_bulk_upsert_mappings_success(
    mock_upsert,
    mock_sync_session: MagicMock,
):
    # Arrange
    payload = [
        {"id": 1, "name": "SyncUpdatedName", "value": 999},
        {"name": "SyncNewUpsert1", "value": 101},
    ]
    upserted_models = [
        MockModel(id=1, name="SyncUpdatedName", value=999),
        MockModel(id=501, name="SyncNewUpsert1", value=101),
    ]

    # --- Mocking the upsert statement chain ---
    mock_upsert_stmt = MagicMock(name="upsert_statement")
    mock_conflict_stmt = MagicMock(name="conflict_statement")
    mock_returning_stmt = MagicMock(name="returning_statement")
    mock_upsert.return_value = mock_upsert_stmt
    mock_upsert_stmt.values.return_value = mock_conflict_stmt
    mock_conflict_stmt.on_conflict_do_update.return_value = mock_returning_stmt
    mock_returning_stmt.returning.return_value = mock_returning_stmt

    # Mock the execution result (session.scalars(...).all())
    mock_sync_session.scalars.return_value.all.return_value = upserted_models

    # Act
    success, results = sync_bulk_upsert_mappings(
        payload=payload, session_inst=mock_sync_session, model=MockModel
    )

    # Assert
    assert success is True
    assert len(results) == len(payload)
    assert results[0].name == "SyncUpdatedName"
    assert results[1].name == "SyncNewUpsert1"

    # Assert mock calls
    mock_upsert.assert_called_once_with(MockModel)
    mock_upsert_stmt.values.assert_called_once_with(payload)
    mock_conflict_stmt.on_conflict_do_update.assert_called_once()
    # ... (further checks if needed) ...
    mock_returning_stmt.returning.assert_called_once_with(MockModel)
    # Check scalars call for retrieving results
    mock_sync_session.scalars.assert_called_once_with(
        mock_returning_stmt, execution_options={"populate_existing": True}
    )
    mock_sync_session.scalars.return_value.all.assert_called_once()
    mock_sync_session.commit.assert_called_once()


# This test now correctly uses the mock_sync_session fixture
@patch("sqlmodel_crud_utils.sync.upsert")
def test_sync_bulk_upsert_mappings_custom_pk(
    mock_upsert,
    mock_sync_session: MagicMock,
):
    # Arrange
    payload = [
        {"name": "SyncCustomPK1", "value": 10},
        {"name": "SyncCustomPK2", "value": 20},
    ]
    pk_fields = ["name", "value"]
    upserted_models = [
        MockModel(id=503, name="SyncCustomPK1", value=10),
        MockModel(id=504, name="SyncCustomPK2", value=20),
    ]

    # --- Mocking the upsert statement chain ---
    mock_upsert_stmt = MagicMock(name="upsert_statement")
    mock_conflict_stmt = MagicMock(name="conflict_statement")
    mock_returning_stmt = MagicMock(name="returning_statement")
    mock_upsert.return_value = mock_upsert_stmt
    mock_upsert_stmt.values.return_value = mock_conflict_stmt
    mock_conflict_stmt.on_conflict_do_update.return_value = mock_returning_stmt
    mock_returning_stmt.returning.return_value = mock_returning_stmt

    # Mock the execution result
    mock_sync_session.scalars.return_value.all.return_value = upserted_models

    # Act
    success, results = sync_bulk_upsert_mappings(
        payload=payload,
        session_inst=mock_sync_session,
        model=MockModel,
        pk_fields=pk_fields,
    )

    # Assert
    assert success is True
    assert len(results) == len(payload)

    # Assert mock calls
    mock_upsert.assert_called_once_with(MockModel)
    mock_upsert_stmt.values.assert_called_once_with(payload)
    mock_conflict_stmt.on_conflict_do_update.assert_called_once()
    call_args, call_kwargs = mock_conflict_stmt.on_conflict_do_update.call_args
    assert "index_elements" in call_kwargs
    assert len(call_kwargs["index_elements"]) == len(pk_fields)
    # ... (further checks if needed) ...
    mock_returning_stmt.returning.assert_called_once_with(MockModel)
    mock_sync_session.scalars.assert_called_once_with(
        mock_returning_stmt, execution_options={"populate_existing": True}
    )
    mock_sync_session.scalars.return_value.all.assert_called_once()
    mock_sync_session.commit.assert_called_once()


# --- Tests for update_row ---


def test_sync_update_row_success(sync_session: Session):
    # Arrange: Create an item to update
    instance = MockModelFactory.build(name="SyncOriginalName", value=100)
    sync_session.add(instance)
    sync_session.commit()
    sync_session.refresh(instance)
    instance_id = instance.id
    update_data = {"name": "SyncUpdatedName", "value": 200}

    # Act: Update the row
    success, row = sync_update_row(
        id_str=instance_id,
        data=update_data,
        session_inst=sync_session,
        model=MockModel,
    )

    # Assert: Check success and returned object
    assert success is True
    assert row is not None
    assert row.id == instance_id
    assert row.name == "SyncUpdatedName"
    assert row.value == 200

    # Assert: Verify the update in the DB
    sync_session.refresh(row)
    assert row.name == "SyncUpdatedName"
    assert row.value == 200


def test_sync_update_row_not_found(sync_session: Session):
    # Arrange: ID that doesn't exist and some update data
    non_existent_id = 99996
    update_data = {"name": "SyncWontBeUpdated"}

    # Act: Try to update the non-existent row
    success, row = sync_update_row(
        id_str=non_existent_id,
        data=update_data,
        session_inst=sync_session,
        model=MockModel,
    )

    # Assert: Check failure
    assert success is False
    assert row is None


# This test now correctly uses the mock_sync_session fixture
def test_sync_update_row_failure(mock_sync_session: MagicMock):
    # Arrange: Mock finding the row but failing on commit
    existing_instance = MockModel(id=1, name="SyncOriginal", value=10)
    update_data = {"name": "SyncUpdated", "value": 20}
    # Configure mock exec().one_or_none()
    mock_sync_session.exec.return_value.one_or_none.return_value = (
        existing_instance
    )
    mock_sync_session.commit.side_effect = Exception("Update DB Error")

    # Act
    with patch("sqlmodel_crud_utils.sync.logger.error") as mock_logger:
        success, row = sync_update_row(
            id_str=1,
            data=update_data,
            session_inst=mock_sync_session,
            model=MockModel,
        )

    # Assert
    assert success is False
    assert row == existing_instance
    assert row.name == "SyncUpdated"
    assert row.value == 20

    # Check mock calls
    mock_sync_session.exec.assert_called_once()
    mock_sync_session.exec.return_value.one_or_none.assert_called_once()
    mock_sync_session.add.assert_called_once_with(existing_instance)
    mock_sync_session.commit.assert_called_once()
    mock_sync_session.rollback.assert_called_once()
    mock_logger.assert_called_once()
    mock_sync_session.refresh.assert_not_called()  # Verify refresh wasn't
    # called on failure path
