"""
Tests for the async functions in `sqlmodel_crud_utils`
"""

from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from sqlmodel import \
    select  # Import Relationship if needed for model definition
from sqlmodel.ext.asyncio.session import AsyncSession

from sqlmodel_crud_utils.a_sync import \
    bulk_upsert_mappings as async_bulk_upsert_mappings
from sqlmodel_crud_utils.a_sync import delete_row as async_delete_row
from sqlmodel_crud_utils.a_sync import \
    get_one_or_create as async_get_one_or_create
from sqlmodel_crud_utils.a_sync import \
    get_result_from_query as async_get_result_from_query
from sqlmodel_crud_utils.a_sync import get_row as async_get_row
from sqlmodel_crud_utils.a_sync import get_rows as async_get_rows
from sqlmodel_crud_utils.a_sync import \
    get_rows_within_id_list as async_get_rows_within_id_list
from sqlmodel_crud_utils.a_sync import \
    insert_data_rows as async_insert_data_rows
from sqlmodel_crud_utils.a_sync import update_row as async_update_row
from sqlmodel_crud_utils.a_sync import write_row as async_write_row

from .conftest import MockModelFactory, MockRelatedModelFactory
from .models import \
    MockModel  # Assuming MockRelatedModel is needed for relationship

# --- Tests for get_result_from_query ---
# (No changes needed for these tests - they use real sessions)


@pytest.mark.asyncio
async def test_async_get_result_from_query_one_result(
    async_session: AsyncSession,
):
    # Arrange: Create a unique item
    instance = MockModelFactory.build()
    async_session.add(instance)
    await async_session.commit()
    await async_session.refresh(instance)

    # Act: Query for the specific item
    statement = select(MockModel).where(MockModel.id == instance.id)
    result = await async_get_result_from_query(statement, async_session)

    # Assert: Check if the correct item is returned
    assert result is not None
    assert result.id == instance.id
    assert result.name == instance.name


@pytest.mark.asyncio
async def test_async_get_result_from_query_no_result(
    async_session: AsyncSession,
):
    # Arrange: Ensure no item exists with a specific ID
    non_existent_id = -99999  # Use a clearly non-existent ID

    # Act: Query for the non-existent item
    statement = select(MockModel).where(MockModel.id == non_existent_id)
    result = await async_get_result_from_query(statement, async_session)

    # Assert: Check if None is returned
    assert result is None


@pytest.mark.asyncio
async def test_async_get_result_from_query_multiple_results(
    async_session: AsyncSession,
):
    # Arrange: Create multiple items with the same name
    common_name = f"MultipleTest-{MockModelFactory.build().id}"
    instance1 = MockModelFactory.build(name=common_name)
    instance2 = MockModelFactory.build(name=common_name)
    async_session.add_all([instance1, instance2])
    await async_session.commit()
    await async_session.refresh(instance1)
    await async_session.refresh(instance2)

    statement = select(MockModel).where(MockModel.name == common_name)
    result = await async_get_result_from_query(statement, async_session)

    # Assert: Check if the first item is returned (as per function logic)
    assert result is not None
    assert result.name == common_name
    # The order isn't guaranteed, so check if the ID is one of the created ones
    assert result.id in [instance1.id, instance2.id]


# --- Tests for get_one_or_create ---


@pytest.mark.asyncio
async def test_async_get_one_or_create_exists(async_session: AsyncSession):
    # Arrange: Create an item
    unique_name = f"ExistingGetOrCreate-{MockModelFactory.build().id}"
    existing_instance = MockModelFactory.build(name=unique_name)
    async_session.add(existing_instance)
    await async_session.commit()
    await async_session.refresh(existing_instance)

    # Act: Call get_one_or_create with the same criteria
    instance, created = await async_get_one_or_create(
        session_inst=async_session,
        model=MockModel,
        name=existing_instance.name,
    )

    # Assert: Check that the existing instance is returned and created is True
    assert instance is not None
    assert instance.id == existing_instance.id
    assert instance.name == existing_instance.name
    assert created is True  # Should be True if found


@pytest.mark.asyncio
async def test_async_get_one_or_create_exists_with_selectin(
    async_session: AsyncSession,
):
    '''
    """
    Test get_one_or_create with selectin=True when the instance exists.
    This test checks if the related field is loaded correctly.
    """

    :param async_session: AsyncSession
    :return:
    '''
    related_instance = MockRelatedModelFactory.build(
        related_name=f"SelectInTestRel-{MockModelFactory.build().id}"
    )
    async_session.add(related_instance)
    await async_session.commit()
    await async_session.refresh(related_instance)

    main_instance = MockModelFactory.build(
        name=f"MainSelectIn-{related_instance.id}",  # Ensure unique name
        related_field_id=related_instance.id,
    )
    async_session.add(main_instance)
    await async_session.commit()
    await async_session.refresh(main_instance)

    # Act: Call get_one_or_create with selectin=True using the relationship name
    # No need to patch getattr if the relationship attribute exists
    instance, created = await async_get_one_or_create(
        session_inst=async_session,
        model=MockModel,
        selectin=True,
        # Use the RELATIONSHIP attribute name here, not the foreign key column
        select_in_key="related_field",
        name=main_instance.name,
    )

    # Assert: Check instance is returned, created is True
    assert instance is not None
    assert created is True  # Should be True as it was found
    assert instance.id == main_instance.id
    assert instance.name == main_instance.name
    assert instance.related_field_id == related_instance.id


@pytest.mark.asyncio
async def test_async_get_one_or_create_does_not_exist(
    async_session: AsyncSession,
):
    # Arrange: Define criteria for a non-existent item
    new_name = (
        f"NewGetOrCreate-{MockModelFactory.build().id}"  # Ensure unique name
    )
    new_value = 456

    # Act: Call get_one_or_create
    instance, created = await async_get_one_or_create(
        session_inst=async_session,
        model=MockModel,
        create_method_kwargs={"value": new_value},
        name=new_name,
    )

    # Assert: Check that a new instance is created and returned, created is
    # False
    assert instance is not None
    assert instance.id is not None  # Should have an ID after commit
    assert instance.name == new_name
    assert instance.value == new_value
    assert created is False  # Should be False as it was created

    # Assert: Verify it exists in the DB now
    fetched_instance = await async_session.get(MockModel, instance.id)
    assert fetched_instance is not None
    assert fetched_instance.name == new_name
    assert fetched_instance.value == new_value


# --- Tests for write_row ---


@pytest.mark.asyncio
async def test_async_write_row_success(async_session: AsyncSession):
    # Arrange: Create a new model instance (not yet saved)
    data_row = MockModelFactory.build(name="WriteMeSuccess")

    # Act: Write the row
    success, result = await async_write_row(data_row, async_session)

    # Assert: Check success and returned object
    assert success is True
    assert result == data_row
    assert result.id is not None

    # Assert: Verify it exists in the DB
    fetched_instance = await async_session.get(MockModel, result.id)
    assert fetched_instance is not None
    assert fetched_instance.name == data_row.name


@pytest.mark.asyncio
async def test_async_write_row_failure(
    mock_async_session: AsyncMock,  # Renamed fixture to avoid confusion
):
    # Arrange
    mock_session = await mock_async_session  # Use the awaited fixture
    data_row = MockModel(name="FailWrite")
    mock_session.commit.side_effect = Exception("DB Error")
    mock_session.rollback.return_value = (
        None  # Ensure rollback is awaitable if needed
    )

    # Act
    with patch("sqlmodel_crud_utils.a_sync.logger.error") as mock_logger:
        # Pass the actual mock session, not the fixture coroutine
        success, result = await async_write_row(data_row, mock_session)

    # Assert
    assert success is False
    assert result is None
    mock_session.add.assert_called_once_with(data_row)
    # Use assert_awaited_once for async methods
    mock_session.commit.assert_awaited_once()
    mock_session.rollback.assert_awaited_once()
    mock_logger.assert_called_once()


# --- Tests for insert_data_rows ---


@pytest.mark.asyncio
async def test_async_insert_data_rows_success(async_session: AsyncSession):
    # Arrange: Create a list of new model instances
    data_rows = MockModelFactory.build_batch(3)
    names_before = {row.name for row in data_rows}
    # Ensure IDs are None before insert
    for row in data_rows:
        row.id = None

    # Act: Insert the rows
    success, result = await async_insert_data_rows(data_rows, async_session)

    # Assert: Check success and returned objects
    assert success is True
    assert result == data_rows
    assert all(row.id is not None for row in result)  # IDs should be populated

    # Assert: Verify they exist in the DB
    ids = [row.id for row in result]
    statement = select(MockModel).where(MockModel.id.in_(ids))
    # FIX: Remove redundant .scalars()
    fetched_rows_result = await async_session.exec(statement)
    fetched_rows = fetched_rows_result.all()
    assert len(fetched_rows) == len(data_rows)
    names_after = {row.name for row in fetched_rows}
    assert names_after == names_before


@pytest.mark.asyncio
async def test_async_insert_data_rows_failure_fallback(
    mock_async_session: AsyncMock,  # Renamed fixture
):
    # Arrange
    mock_session = await mock_async_session  # Use the awaited fixture
    data_rows = [MockModel(id=1, name="Row1"), MockModel(id=2, name="Row2")]
    # Make commit and rollback awaitable mocks
    mock_session.commit = AsyncMock(
        side_effect=[
            Exception("Bulk DB Error"),
            None,  # Success for row 1
            Exception("Single DB Error"),  # Failure for row 2
        ]
    )
    mock_session.rollback = AsyncMock(
        side_effect=[
            None,
            None,
        ]
    )

    # Act
    with (
        patch("sqlmodel_crud_utils.a_sync.logger.error") as mock_logger_error,
        patch("sqlmodel_crud_utils.a_sync.logger.info") as mock_logger_info,
    ):
        # Pass the actual mock session
        success, result = await async_insert_data_rows(data_rows, mock_session)

    # Assert
    assert success is True  # Fallback succeeded for at least one row
    assert len(result["success"]) == 1
    assert result["success"][0].name == "Row1"
    assert len(result["failed"]) == 1
    assert result["failed"][0].name == "Row2"

    # Check mock calls
    mock_session.add_all.assert_called_once_with(data_rows)
    assert mock_session.commit.await_count == 3
    assert mock_session.rollback.await_count == 2
    # The add calls happen within the fallback write_row
    assert mock_session.add.call_count == 2
    mock_session.add.assert_has_calls(
        [call(data_rows[0]), call(data_rows[1])], any_order=False
    )
    assert mock_logger_error.call_count == 2  # Bulk error + single error
    mock_logger_info.assert_called_once()  # Info about fallback


@pytest.mark.asyncio
async def test_async_insert_data_rows_failure_all_fallback_fail(
    mock_async_session: AsyncMock,  # Renamed fixture
):
    # Arrange
    mock_session = await mock_async_session  # Use the awaited fixture
    data_rows = [MockModel(id=1, name="Row1"), MockModel(id=2, name="Row2")]
    # Make commit and rollback awaitable mocks
    mock_session.commit = AsyncMock(
        side_effect=[
            Exception("Bulk DB Error"),
            Exception("Single DB Error 1"),
            Exception("Single DB Error 2"),
        ]
    )
    mock_session.rollback = AsyncMock(
        side_effect=[
            None,  # After bulk fail
            None,  # After single fail 1
            None,  # After single fail 2
        ]
    )

    # Act
    with (
        patch("sqlmodel_crud_utils.a_sync.logger.error") as mock_logger_error,
        patch("sqlmodel_crud_utils.a_sync.logger.info") as mock_logger_info,
    ):
        # Pass the actual mock session
        success, result = await async_insert_data_rows(data_rows, mock_session)

    # Assert
    assert success == (False,)  # Special return value for all fallback fails
    assert len(result["success"]) == 0
    assert len(result["failed"]) == 2
    assert result["failed"] == data_rows

    # Check mock calls
    mock_session.add_all.assert_called_once_with(data_rows)
    assert mock_session.commit.await_count == 3
    assert mock_session.rollback.await_count == 3
    assert mock_session.add.call_count == 2
    mock_session.add.assert_has_calls(
        [call(data_rows[0]), call(data_rows[1])], any_order=False
    )
    assert mock_logger_error.call_count == 3  # Bulk error + 2 single errors
    mock_logger_info.assert_called_once()  # Info about fallback


# --- Tests for get_row ---


@pytest.mark.asyncio
async def test_async_get_row_found(async_session: AsyncSession):
    # Arrange: Create an item
    instance = MockModelFactory.build(
        name=f"GetRowFound-{MockModelFactory.build().id}"
    )
    async_session.add(instance)
    await async_session.commit()
    await async_session.refresh(instance)

    # Act: Get the row by ID
    success, row = await async_get_row(
        id_str=instance.id, session_inst=async_session, model=MockModel
    )

    # Assert: Check success and data
    assert success is True
    assert row is not None
    assert row.id == instance.id
    assert row.name == instance.name


@pytest.mark.asyncio
async def test_async_get_row_not_found(async_session: AsyncSession):
    # Arrange: ID that doesn't exist
    non_existent_id = -99998

    # Act: Try to get the row
    success, row = await async_get_row(
        id_str=non_existent_id, session_inst=async_session, model=MockModel
    )

    # Assert: Check failure
    assert success is False
    assert row is None


@pytest.mark.asyncio
async def test_async_get_row_with_options(async_session: AsyncSession):
    # Arrange: Create related and main instances
    # NOTE: Assumes MockModel has a relationship 'related_field'
    related = MockRelatedModelFactory.build(
        related_name=f"WithOptionsRel-{MockModelFactory.build().id}"
    )
    async_session.add(related)
    await async_session.commit()
    await async_session.refresh(related)

    main = MockModelFactory.build(
        name=f"WithOptionsMain-{related.id}", related_field_id=related.id
    )
    async_session.add(main)
    await async_session.commit()
    await async_session.refresh(main)

    # Act: Get the row with options using the relationship name
    # No need to patch getattr if relationship exists
    success, row = await async_get_row(
        id_str=main.id,
        session_inst=async_session,
        model=MockModel,
        selectin=True,
        # Use RELATIONSHIP name
        select_in_keys=["related_field"],
    )

    # Assert: Check success and data accessibility
    assert success is True
    assert row is not None
    assert row.id == main.id
    assert row.related_field_id == related.id
    # Optional: Check relationship loaded
    # assert row.related_field is not None
    # assert row.related_field.id == related.id


# --- Tests for get_rows ---
# NOTE: These tests might still fail if the async_session fixture
# doesn't properly isolate test runs (clean the DB).


@pytest.mark.asyncio
async def test_async_get_rows_basic(async_session: AsyncSession):
    # Arrange: Create some data with unique names for this test
    batch_size = 5
    unique_prefix = f"Basic-{MockModelFactory.build().id}"
    instances = MockModelFactory.build_batch(batch_size)
    inst_array = []
    for i, inst in enumerate(instances):
        row = MockModel(
            **inst.model_dump(exclude={"id", "name"}),
            name=f"{unique_prefix}-{i}",
        )
        row.id = None  # Ensure IDs are generated by DB
        inst_array.append(row)
    instances = inst_array
    async_session.add_all(instances)
    await async_session.commit()

    # Act: Get the rows matching the unique prefix
    success, rows = await async_get_rows(
        session_inst=async_session,
        model=MockModel,
        name__like=f"{unique_prefix}-%",
    )

    # Assert: Check success and that the correct number of rows are returned
    assert success is True
    assert isinstance(rows, list)
    assert len(rows) == batch_size


@pytest.mark.asyncio
async def test_async_get_rows_pagination(async_session: AsyncSession):
    # Arrange: Create enough data for pagination with unique names
    batch_size = 25
    unique_prefix = f"Paginate-{MockModelFactory.build().id}"
    instances = MockModelFactory.build_batch(batch_size)
    inst_array = []
    for i, inst in enumerate(instances):
        row = MockModel(
            **inst.model_dump(exclude={"id", "name"}),
            name=f"{unique_prefix}-{i}",
        )
        row.id = None  # Ensure IDs are generated by DB
        inst_array.append(row)
    instances = inst_array
    async_session.add_all(instances)
    await async_session.commit()
    for inst in instances:
        await async_session.refresh(inst)  # Get IDs

    # Get IDs only for the created batch
    all_ids_sorted = sorted([inst.id for inst in instances])

    page_size = 10
    page = 2
    offset = (page - 1) * page_size
    expected_ids = all_ids_sorted[offset : offset + page_size]

    # Act: Get a specific page, filtering by unique prefix
    success, rows = await async_get_rows(
        session_inst=async_session,
        model=MockModel,
        page_size=page_size,
        page=page,
        sort_field="id",  # Sorting by ID is crucial for pagination consistency
        name__like=f"{unique_prefix}-%",  # Filter to isolate test data
    )

    # Assert: Check success and compare IDs
    assert success is True
    assert len(rows) == len(expected_ids)
    assert [row.id for row in rows] == expected_ids


@pytest.mark.asyncio
async def test_async_get_rows_with_filters_and_sort(
    async_session: AsyncSession,
):
    # Arrange: Create specific data with unique names
    unique_prefix = f"FilterSort-{MockModelFactory.build().id}"
    target_name = f"{unique_prefix}-Target"
    other_name = f"{unique_prefix}-Other"
    instances = [
        MockModelFactory.build(name=target_name, value=50),
        MockModelFactory.build(name=target_name, value=150),
        MockModelFactory.build(name=other_name, value=100),
        MockModelFactory.build(
            name=target_name, value=20
        ),  # Should be filtered out by value__gte
    ]
    for inst in instances:
        inst.id = None
    async_session.add_all(instances)
    await async_session.commit()
    for inst in instances:
        await async_session.refresh(inst)  # Get IDs if needed

    expected_ids_values = sorted(
        [
            (inst.id, inst.value)
            for inst in instances
            if inst.name == target_name and inst.value >= 50
        ],
        key=lambda x: x[1],
        reverse=True,  # Sort by value desc
    )

    # Act: Get rows with filters and sorting
    # No need to patch getattr if using supported filter suffixes
    success, rows = await async_get_rows(
        session_inst=async_session,
        model=MockModel,
        name=target_name,  # Exact match filter
        value__gte=50,  # Greater than or equal filter
        sort_field="value",
        sort_desc=True,
    )

    # Assert: Check success and results
    assert success is True
    assert len(rows) == 2
    assert [(row.id, row.value) for row in rows] == expected_ids_values
    # Explicit checks based on expected sort order
    assert rows[0].name == target_name
    assert rows[1].name == target_name
    assert rows[0].value == 150
    assert rows[1].value == 50


@pytest.mark.asyncio
async def test_async_get_rows_no_results(async_session: AsyncSession):
    # Arrange: Use a filter guaranteed to find nothing
    non_existent_name = (
        f"ThisNameDoesNotExistForSure-{MockModelFactory.build().id}"
    )

    # Optional: Verify it doesn't exist first (good practice)
    existing_check = await async_session.exec(
        select(MockModel).where(MockModel.name == non_existent_name)
    )
    assert existing_check.first() is None

    # Act: Get rows with the filter
    success, rows = await async_get_rows(
        session_inst=async_session, model=MockModel, name=non_existent_name
    )

    # Assert: Check success is False and empty list
    assert success is False
    assert rows == []


# --- Tests for get_rows_within_id_list ---


@pytest.mark.asyncio
async def test_async_get_rows_within_id_list_found(async_session: AsyncSession):
    # Arrange: Create some items and get their IDs
    instances = MockModelFactory.build_batch(3)
    for inst in instances:
        inst.id = None
    async_session.add_all(instances)
    await async_session.commit()
    ids_to_find = []
    for inst in instances:
        await async_session.refresh(inst)
        ids_to_find.append(inst.id)

    # Create an extra item that should NOT be found
    extra_instance = MockModelFactory.build(
        name=f"Extra-{MockModelFactory.build().id}"
    )
    extra_instance.id = None
    async_session.add(extra_instance)
    await async_session.commit()
    await async_session.refresh(extra_instance)

    # Act: Get rows with the list of IDs
    # No need to patch getattr
    success, results_proxy = await async_get_rows_within_id_list(
        id_str_list=ids_to_find, session_inst=async_session, model=MockModel
    )
    # FIX: Remove redundant .scalars()
    results = results_proxy.all()

    # Assert: Check success and that the correct rows were found
    assert (
        success is True
    )  # Should be true if the query ran, even if results were empty
    assert len(results) == len(ids_to_find)
    assert {row.id for row in results} == set(ids_to_find)


@pytest.mark.asyncio
async def test_async_get_rows_within_id_list_not_found(
    async_session: AsyncSession,
):
    # Arrange: List of IDs guaranteed not to exist
    non_existent_ids = [-1, -2, -3]

    # Act: Get rows with the non-existent IDs
    # No need to patch getattr
    success, results_proxy = await async_get_rows_within_id_list(
        id_str_list=non_existent_ids,
        session_inst=async_session,
        model=MockModel,
    )
    # FIX: Remove redundant .scalars()
    results = results_proxy.all()

    # Assert: Check success (should be True as query ran) and empty results
    assert (
        success is True
    )  # The function's success indicates query execution, not finding rows
    assert results == []


# --- Tests for delete_row ---


@pytest.mark.asyncio
async def test_async_delete_row_success(async_session: AsyncSession):
    # Arrange: Create an item to delete
    instance = MockModelFactory.build(
        name=f"ToDelete-{MockModelFactory.build().id}"
    )
    instance.id = None
    async_session.add(instance)
    await async_session.commit()
    await async_session.refresh(instance)
    instance_id = instance.id
    assert instance_id is not None  # Sanity check

    # Act: Delete the row
    success = await async_delete_row(
        id_str=instance_id, session_inst=async_session, model=MockModel
    )

    # Assert: Check success
    assert success is True

    # Assert: Verify it's gone from the DB
    fetched_instance = await async_session.get(MockModel, instance_id)
    assert fetched_instance is None


@pytest.mark.asyncio
async def test_async_delete_row_not_found(async_session: AsyncSession):
    # Arrange: ID that doesn't exist
    non_existent_id = -99997

    # Act: Try to delete the non-existent row
    success = await async_delete_row(
        id_str=non_existent_id, session_inst=async_session, model=MockModel
    )

    # Assert: Check failure
    assert success is False


@pytest.mark.asyncio
async def test_async_delete_row_failure(
    mock_async_session: AsyncMock,  # Renamed fixture
):
    # Arrange: Mock finding the row but failing on commit
    mock_session = await mock_async_session  # Use the awaited fixture
    mock_instance = MockModel(id=1, name="ToDeleteFail")

    # Configure the mock exec().one_or_none() chain (assuming get_row uses this)
    # Or mock the get call if delete_row uses session.get
    # Let's assume it uses select -> exec -> one_or_none based on sync version
    mock_exec_result = MagicMock()
    mock_exec_result.one_or_none.return_value = mock_instance
    mock_session.exec = AsyncMock(return_value=mock_exec_result)

    # Make commit and rollback awaitable mocks
    mock_session.commit = AsyncMock(side_effect=Exception("Delete DB Error"))
    mock_session.rollback = AsyncMock(return_value=None)

    # Act
    with patch("sqlmodel_crud_utils.a_sync.logger.error") as mock_logger:
        # Pass the actual mock session
        success = await async_delete_row(
            id_str=1, session_inst=mock_session, model=MockModel
        )

    # Assert
    assert success is False
    # Check mock calls
    mock_session.exec.assert_awaited_once()  # Check exec was called
    mock_exec_result.one_or_none.assert_called_once()  # Check one_or_none
    # was called
    mock_session.delete.assert_called_once_with(mock_instance)
    mock_session.commit.assert_awaited_once()
    mock_session.rollback.assert_awaited_once()
    mock_logger.assert_called_once()


# --- Tests for bulk_upsert_mappings ---


@pytest.mark.asyncio
@patch("sqlmodel_crud_utils.a_sync.upsert")
async def test_async_bulk_upsert_mappings_success(
    mock_upsert,
    mock_async_session: AsyncMock,  # Renamed fixture
):
    # Arrange
    mock_session = await mock_async_session  # Use the awaited fixture
    payload = [
        {"id": 1, "name": "UpdatedName", "value": 999},
        {"name": "NewUpsert1", "value": 101},  # Insert case (no ID)
    ]
    upserted_models = [
        MockModel(id=1, name="UpdatedName", value=999),
        MockModel(
            id=501, name="NewUpsert1", value=101
        ),  # Assume DB assigns ID 501
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
    mock_scalars_result = MagicMock()
    mock_scalars_result.all.return_value = upserted_models
    # Make scalars awaitable and return the mock result
    mock_session.scalars = AsyncMock(return_value=mock_scalars_result)
    # Make commit awaitable
    mock_session.commit = AsyncMock(return_value=None)

    # Act
    success, results = await async_bulk_upsert_mappings(
        payload=payload, session_inst=mock_session, model=MockModel
    )

    # Assert
    assert success is True
    assert len(results) == len(payload)
    assert results[0].name == "UpdatedName"
    assert results[1].name == "NewUpsert1"

    # Assert mock calls
    mock_upsert.assert_called_once_with(MockModel)
    mock_upsert_stmt.values.assert_called_once_with(payload)
    mock_conflict_stmt.on_conflict_do_update.assert_called_once()
    # Add more specific checks for on_conflict_do_update args if needed
    # e.g., check index_elements=[MockModel.id], set_={...}
    mock_returning_stmt.returning.assert_called_once_with(MockModel)
    mock_session.scalars.assert_awaited_once_with(
        mock_returning_stmt, execution_options={"populate_existing": True}
    )
    mock_scalars_result.all.assert_called_once()
    mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
@patch("sqlmodel_crud_utils.a_sync.upsert")
async def test_async_bulk_upsert_mappings_custom_pk(
    mock_upsert,
    mock_async_session: AsyncMock,  # Renamed fixture
):
    # Arrange
    mock_session = await mock_async_session  # Use the awaited fixture
    payload = [
        {"name": "CustomPK1", "value": 10},
        {"name": "CustomPK2", "value": 20},
    ]
    pk_fields = ["name", "value"]  # Custom composite PK
    upserted_models = [
        MockModel(id=503, name="CustomPK1", value=10),  # Assume DB assigns IDs
        MockModel(id=504, name="CustomPK2", value=20),
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
    mock_scalars_result = MagicMock()
    mock_scalars_result.all.return_value = upserted_models
    mock_session.scalars = AsyncMock(return_value=mock_scalars_result)
    mock_session.commit = AsyncMock(return_value=None)

    # Act
    success, results = await async_bulk_upsert_mappings(
        payload=payload,
        session_inst=mock_session,
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
    # Check args passed to on_conflict_do_update
    call_args, call_kwargs = mock_conflict_stmt.on_conflict_do_update.call_args
    assert "index_elements" in call_kwargs
    assert len(call_kwargs["index_elements"]) == len(pk_fields)

    assert "set_" in call_kwargs  # Check if set_ clause was generated
    mock_returning_stmt.returning.assert_called_once_with(MockModel)
    mock_session.scalars.assert_awaited_once_with(
        mock_returning_stmt, execution_options={"populate_existing": True}
    )
    mock_scalars_result.all.assert_called_once()
    mock_session.commit.assert_awaited_once()


# --- Tests for update_row ---


@pytest.mark.asyncio
async def test_async_update_row_success(async_session: AsyncSession):
    # Arrange: Create an item to update
    original_name = f"OriginalName-{MockModelFactory.build().id}"
    instance = MockModelFactory.build(name=original_name, value=100)
    instance.id = None
    async_session.add(instance)
    await async_session.commit()
    await async_session.refresh(instance)
    instance_id = instance.id
    updated_name = f"UpdatedName-{instance_id}"
    update_data = {"name": updated_name, "value": 200}

    # Act: Update the row
    success, row = await async_update_row(
        id_str=instance_id,
        data=update_data,
        session_inst=async_session,
        model=MockModel,
    )

    # Assert: Check success and returned object
    assert success is True
    assert row is not None
    assert row.id == instance_id
    assert row.name == updated_name
    assert row.value == 200

    # Assert: Verify the update in the DB by refreshing the object from session
    await async_session.refresh(row)  # Refresh the returned row object
    assert row.name == updated_name
    assert row.value == 200

    # Optional: Verify by fetching again
    fetched_instance = await async_session.get(MockModel, instance_id)
    assert fetched_instance is not None
    assert fetched_instance.name == updated_name
    assert fetched_instance.value == 200


@pytest.mark.asyncio
async def test_async_update_row_not_found(async_session: AsyncSession):
    # Arrange: ID that doesn't exist and some update data
    non_existent_id = -99996
    update_data = {"name": "WontBeUpdated"}

    # Act: Try to update the non-existent row
    success, row = await async_update_row(
        id_str=non_existent_id,
        data=update_data,
        session_inst=async_session,
        model=MockModel,
    )

    # Assert: Check failure
    assert success is False
    assert row is None


@pytest.mark.asyncio
async def test_async_update_row_failure(
    mock_async_session: AsyncMock,  # Renamed fixture
):
    # Arrange: Mock finding the row but failing on commit
    mock_session = await mock_async_session  # Use the awaited fixture
    existing_instance = MockModel(id=1, name="Original", value=10)
    update_data = {"name": "Updated", "value": 20}

    # Configure mock exec().one_or_none() (assuming update_row uses this)
    mock_exec_result = MagicMock()
    mock_exec_result.one_or_none.return_value = existing_instance
    mock_session.exec = AsyncMock(return_value=mock_exec_result)

    # Make commit and rollback awaitable mocks
    mock_session.commit = AsyncMock(side_effect=Exception("Update DB Error"))
    mock_session.rollback = AsyncMock(return_value=None)

    # Act
    with patch("sqlmodel_crud_utils.a_sync.logger.error") as mock_logger:
        # Pass the actual mock session
        success, row = await async_update_row(
            id_str=1,
            data=update_data,
            session_inst=mock_session,
            model=MockModel,
        )

    # Assert
    assert success is False
    # The row object IS modified in place before the commit fails
    assert row is existing_instance
    assert row.name == "Updated"
    assert row.value == 20

    # Check mock calls
    mock_session.exec.assert_awaited_once()
    mock_exec_result.one_or_none.assert_called_once()
    mock_session.add.assert_called_once_with(
        existing_instance
    )  # Add is called before commit
    mock_session.commit.assert_awaited_once()
    mock_session.rollback.assert_awaited_once()
    mock_logger.assert_called_once()
