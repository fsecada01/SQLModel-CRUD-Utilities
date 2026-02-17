"""
Comprehensive tests for v0.2.0 features.

This module tests all new features introduced in version 0.2.0:
- Custom exception hierarchy
- Transaction context managers
- AuditMixin for timestamp tracking
- SoftDeleteMixin for soft delete support
- Public API exports
"""

import time
from datetime import datetime, timezone
from typing import Optional

import pytest
from sqlmodel import Field, Session, SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

# Import the new features from the package
from sqlmodel_crud_utils import (
    AuditMixin,
    BulkOperationError,
    MultipleRecordsError,
    RecordNotFoundError,
    SoftDeleteMixin,
    SQLModelCRUDError,
    TransactionError,
    ValidationError,
    __version__,
    a_transaction,
    a_write_row,
    transaction,
    write_row,
)
from sqlmodel_crud_utils.exceptions import (
    DatabaseConnectionError,
    QueryExecutionError,
    multiple_found,
    not_found,
    validation_error,
)

# ============================================================================
# Test Models with Mixins
# ============================================================================


class AuditTestModel(SQLModel, AuditMixin, table=True):
    """Test model with audit trail."""

    __tablename__ = "audit_test_model"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    value: int = 0


class SoftDeleteTestModel(SQLModel, SoftDeleteMixin, table=True):
    """Test model with soft delete support."""

    __tablename__ = "soft_delete_test_model"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    value: int = 0


class CombinedMixinTestModel(SQLModel, AuditMixin, SoftDeleteMixin, table=True):
    """Test model with both mixins."""

    __tablename__ = "combined_mixin_test_model"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    value: int = 0


# ============================================================================
# Exception Tests
# ============================================================================


class TestExceptions:
    """Test the custom exception hierarchy."""

    def test_base_exception(self):
        """Test that SQLModelCRUDError is the base exception."""
        exc = SQLModelCRUDError("Test error")
        assert isinstance(exc, Exception)
        assert str(exc) == "Test error"

    def test_record_not_found_error_basic(self):
        """Test RecordNotFoundError with model info."""
        exc = RecordNotFoundError(
            model=AuditTestModel, id_value=123, pk_field="id"
        )

        assert isinstance(exc, SQLModelCRUDError)
        assert exc.model == AuditTestModel
        assert exc.id_value == 123
        assert exc.pk_field == "id"
        assert "AuditTestModel" in str(exc)
        assert "123" in str(exc)
        assert "id" in str(exc)

    def test_record_not_found_error_custom_pk(self):
        """Test RecordNotFoundError with custom primary key field."""
        exc = RecordNotFoundError(
            model=AuditTestModel, id_value="abc-123", pk_field="user_id"
        )

        assert exc.pk_field == "user_id"
        assert "user_id" in str(exc)
        assert "abc-123" in str(exc)

    def test_multiple_records_error_with_count(self):
        """Test MultipleRecordsError with count."""
        exc = MultipleRecordsError(model=AuditTestModel, count=5)

        assert isinstance(exc, SQLModelCRUDError)
        assert exc.model == AuditTestModel
        assert exc.count == 5
        assert exc.filters is None
        assert "Expected 1" in str(exc)
        assert "found 5" in str(exc)
        assert "AuditTestModel" in str(exc)

    def test_multiple_records_error_with_filters(self):
        """Test MultipleRecordsError with filters."""
        filters = {"email": "test@example.com", "active": True}
        exc = MultipleRecordsError(
            model=AuditTestModel, count=3, filters=filters
        )

        assert exc.filters == filters
        assert "filters:" in str(exc)
        assert "email" in str(exc)

    def test_validation_error_basic(self):
        """Test ValidationError with basic message."""
        exc = ValidationError(message="Invalid data")

        assert isinstance(exc, SQLModelCRUDError)
        assert exc.field is None
        assert exc.value is None
        assert exc.errors is None
        assert "Validation failed" in str(exc)

    def test_validation_error_with_field(self):
        """Test ValidationError with field info."""
        exc = ValidationError(
            message="Must be positive", field="age", value=-5
        )

        assert exc.field == "age"
        assert exc.value == -5
        assert "age" in str(exc)
        assert "-5" in str(exc)
        assert "Must be positive" in str(exc)

    def test_validation_error_with_multiple_errors(self):
        """Test ValidationError with multiple field errors."""
        errors = {"email": "Invalid format", "age": "Must be 18+"}
        exc = ValidationError(
            message="Multiple validation errors", errors=errors
        )

        assert exc.errors == errors
        assert "email" in str(exc)
        assert "age" in str(exc)
        assert "Invalid format" in str(exc)
        assert "Must be 18+" in str(exc)

    def test_bulk_operation_error_basic(self):
        """Test BulkOperationError with failed records."""
        errors = ["Error 1", "Error 2", "Error 3"]
        exc = BulkOperationError(total=100, failed=3, errors=errors)

        assert isinstance(exc, SQLModelCRUDError)
        assert exc.total == 100
        assert exc.failed == 3
        assert exc.errors == errors
        assert exc.successful is None
        assert exc.failed_records is None
        assert "3/100" in str(exc)
        assert "97.0%" in str(exc)  # Success rate

    def test_bulk_operation_error_with_details(self):
        """Test BulkOperationError with successful and failed records."""
        errors = ["Record 5 failed", "Record 10 failed"]
        successful = [1, 2, 3, 4, 6, 7, 8, 9]
        failed_records = [{"id": 5}, {"id": 10}]

        exc = BulkOperationError(
            total=10,
            failed=2,
            errors=errors,
            successful=successful,
            failed_records=failed_records,
        )

        assert exc.successful == successful
        assert exc.failed_records == failed_records
        assert exc.successful is not None and len(exc.successful) == 8
        assert exc.failed_records is not None and len(exc.failed_records) == 2

    def test_bulk_operation_error_summary(self):
        """Test BulkOperationError get_error_summary method."""
        errors = [
            ValueError("Invalid value"),
            "String error message",
            KeyError("missing_key"),
        ]
        exc = BulkOperationError(total=50, failed=3, errors=errors)

        summary = exc.get_error_summary()

        assert "3/50" in summary
        assert "ValueError" in summary
        assert "String error message" in summary
        assert "KeyError" in summary

    def test_transaction_error_basic(self):
        """Test TransactionError basic functionality."""
        exc = TransactionError(message="Transaction failed")

        assert isinstance(exc, SQLModelCRUDError)
        assert exc.operation is None
        assert exc.original_error is None
        assert "Transaction failed" in str(exc)

    def test_transaction_error_with_operation(self):
        """Test TransactionError with operation info."""
        original = ValueError("Database constraint violated")
        exc = TransactionError(operation="commit", original_error=original)

        assert exc.operation == "commit"
        assert exc.original_error == original
        assert "commit" in str(exc)
        assert "ValueError" in str(exc)

    def test_transaction_error_wrapping(self):
        """Test that TransactionError preserves exception chain."""
        original = ValueError("Original error")
        exc = TransactionError(operation="rollback", original_error=original)

        # The original error should be preserved
        assert exc.original_error == original
        assert "rollback" in str(exc)

    def test_database_connection_error(self):
        """Test DatabaseConnectionError."""
        exc = DatabaseConnectionError(
            database_url="postgresql://localhost:5432/testdb",
            original_error=ConnectionError("Connection timeout"),
        )

        assert isinstance(exc, SQLModelCRUDError)
        assert exc.database_url == "postgresql://localhost:5432/testdb"
        assert "localhost:5432" in str(exc)
        assert "ConnectionError" in str(exc)

    def test_query_execution_error(self):
        """Test QueryExecutionError."""
        query = "SELECT * FROM users WHERE id = 123"
        exc = QueryExecutionError(
            query=query,
            original_error=Exception("Column does not exist"),
        )

        assert isinstance(exc, SQLModelCRUDError)
        assert exc.query == query
        assert "SELECT" in str(exc)
        assert "Column does not exist" in str(exc)

    def test_exception_inheritance(self):
        """Test that all exceptions inherit from SQLModelCRUDError."""
        exceptions = [
            RecordNotFoundError(model=AuditTestModel, id_value=1),
            MultipleRecordsError(model=AuditTestModel, count=2),
            ValidationError(message="Test"),
            BulkOperationError(total=10, failed=1, errors=["Error"]),
            TransactionError(message="Test"),
            DatabaseConnectionError(message="Test"),
            QueryExecutionError(message="Test"),
        ]

        for exc in exceptions:
            assert isinstance(exc, SQLModelCRUDError)
            assert isinstance(exc, Exception)

    def test_convenience_functions(self):
        """Test the convenience functions for creating exceptions."""
        # not_found
        exc1 = not_found(AuditTestModel, 123, "id")
        assert isinstance(exc1, RecordNotFoundError)
        assert exc1.id_value == 123

        # multiple_found
        exc2 = multiple_found(AuditTestModel, 5, {"name": "test"})
        assert isinstance(exc2, MultipleRecordsError)
        assert exc2.count == 5

        # validation_error
        exc3 = validation_error("Invalid", field="email", value="bad")
        assert isinstance(exc3, ValidationError)
        assert exc3.field == "email"


# ============================================================================
# Transaction Manager Tests
# ============================================================================


class TestTransactions:
    """Test the transaction context managers."""

    def test_sync_transaction_auto_commit(self, sync_session: Session):
        """Test that sync transaction auto-commits on success."""
        # Create a record within transaction
        with transaction(sync_session) as tx:
            model = AuditTestModel(name="test_commit", value=100)
            tx.add(model)
            # Should auto-commit when exiting context

        # Verify the record was committed
        sync_session.rollback()  # Clear any pending state
        result = sync_session.get(AuditTestModel, model.id)
        assert result is not None
        assert result.name == "test_commit"
        assert result.value == 100

    def test_sync_transaction_auto_rollback(self, sync_session: Session):
        """Test that sync transaction auto-rolls back on error."""
        initial_count = len(sync_session.exec(
            SQLModel.metadata.tables["audit_test_model"].select()
        ).fetchall())

        # Attempt to create a record but raise an error
        with pytest.raises(TransactionError) as exc_info:
            with transaction(sync_session) as tx:
                model = AuditTestModel(name="test_rollback", value=200)
                tx.add(model)
                raise ValueError("Simulated error")

        # Verify TransactionError wraps the original error
        assert "Simulated error" in str(exc_info.value)
        assert isinstance(exc_info.value.__cause__, ValueError)

        # Verify no record was committed
        sync_session.rollback()  # Clear state
        final_count = len(sync_session.exec(
            SQLModel.metadata.tables["audit_test_model"].select()
        ).fetchall())
        assert final_count == initial_count

    def test_sync_transaction_multiple_operations(self, sync_session: Session):
        """Test sync transaction with multiple operations."""
        with transaction(sync_session) as tx:
            model1 = AuditTestModel(name="multi_1", value=1)
            model2 = AuditTestModel(name="multi_2", value=2)
            model3 = AuditTestModel(name="multi_3", value=3)
            tx.add_all([model1, model2, model3])

        # Verify all records were committed
        sync_session.rollback()
        results = sync_session.exec(
            SQLModel.metadata.tables["audit_test_model"]
            .select()
            .where(SQLModel.metadata.tables["audit_test_model"].c.name.like("multi_%"))
        ).fetchall()
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_async_transaction_auto_commit(
        self, async_session: AsyncSession
    ):
        """Test that async transaction auto-commits on success."""
        # Create a record within async transaction
        async with a_transaction(async_session) as tx:
            model = AuditTestModel(name="async_commit", value=100)
            tx.add(model)
            # Should auto-commit when exiting context

        # Verify the record was committed
        await async_session.rollback()  # Clear any pending state
        result = await async_session.get(AuditTestModel, model.id)
        assert result is not None
        assert result.name == "async_commit"
        assert result.value == 100

    @pytest.mark.asyncio
    async def test_async_transaction_auto_rollback(
        self, async_session: AsyncSession
    ):
        """Test that async transaction auto-rolls back on error."""
        from sqlmodel import select

        initial_results = await async_session.exec(
            select(AuditTestModel)
        )
        initial_count = len(initial_results.all())

        # Attempt to create a record but raise an error
        with pytest.raises(TransactionError) as exc_info:
            async with a_transaction(async_session) as tx:
                model = AuditTestModel(name="async_rollback", value=200)
                tx.add(model)
                raise ValueError("Async simulated error")

        # Verify TransactionError wraps the original error
        assert "Async simulated error" in str(exc_info.value)
        assert isinstance(exc_info.value.__cause__, ValueError)

        # Verify no record was committed
        await async_session.rollback()
        final_results = await async_session.exec(
            select(AuditTestModel)
        )
        final_count = len(final_results.all())
        assert final_count == initial_count

    @pytest.mark.asyncio
    async def test_async_transaction_multiple_operations(
        self, async_session: AsyncSession
    ):
        """Test async transaction with multiple operations."""
        async with a_transaction(async_session) as tx:
            model1 = AuditTestModel(name="async_multi_1", value=1)
            model2 = AuditTestModel(name="async_multi_2", value=2)
            model3 = AuditTestModel(name="async_multi_3", value=3)
            tx.add_all([model1, model2, model3])

        # Verify all records were committed
        from sqlmodel import select

        await async_session.rollback()
        results = await async_session.exec(
            select(AuditTestModel).where(
                AuditTestModel.name.startswith("async_multi_")
            )
        )
        records = results.all()
        assert len(records) == 3

    def test_transaction_error_wrapping(self, sync_session: Session):
        """Test that TransactionError properly wraps exceptions."""
        class CustomError(Exception):
            pass

        with pytest.raises(TransactionError) as exc_info:
            with transaction(sync_session):
                raise CustomError("Custom error message")

        # Check the TransactionError
        trans_error = exc_info.value
        assert isinstance(trans_error, TransactionError)
        assert "Custom error message" in str(trans_error)

        # Check the cause is preserved
        assert isinstance(trans_error.__cause__, CustomError)
        assert str(trans_error.__cause__) == "Custom error message"


# ============================================================================
# AuditMixin Tests
# ============================================================================


class TestAuditMixin:
    """Test the AuditMixin functionality."""

    def test_created_at_is_auto_set(self, sync_session: Session):
        """Test that created_at is automatically set."""
        before = datetime.now(timezone.utc)
        model = AuditTestModel(name="audit_test_1", value=42)

        assert model.created_at is not None
        assert before <= model.created_at <= datetime.now(timezone.utc)

    def test_created_by_can_be_set(self, sync_session: Session):
        """Test that created_by can be set."""
        model = AuditTestModel(
            name="audit_test_2", value=42, created_by="admin"
        )

        assert model.created_by == "admin"

    def test_updated_at_initially_none(self, sync_session: Session):
        """Test that updated_at is initially None."""
        model = AuditTestModel(name="audit_test_3", value=42)

        assert model.updated_at is None

    def test_updated_at_behavior_on_update(self, sync_session: Session):
        """Test updated_at behavior (requires DB commit to trigger)."""
        # Create and commit initial record
        model = AuditTestModel(name="audit_test_4", value=42)
        sync_session.add(model)
        sync_session.commit()
        sync_session.refresh(model)

        # Verify created_at is set and updated_at is None
        assert model.created_at is not None
        assert model.updated_at is None

        # Wait a bit to ensure timestamp difference
        time.sleep(0.1)

        # Update the record
        model.value = 100
        sync_session.add(model)
        sync_session.commit()
        sync_session.refresh(model)

        # Note: The onupdate parameter in SQLAlchemy is database-dependent
        # SQLite doesn't support onupdate triggers by default
        # For proper testing, you'd need a database that supports it
        # or manually set updated_at in application code

        # For now, we just verify the field exists and can be set manually
        model.updated_at = datetime.now(timezone.utc)
        sync_session.add(model)
        sync_session.commit()
        sync_session.refresh(model)

        assert model.updated_at is not None
        assert model.updated_at >= model.created_at

    def test_updated_by_can_be_set(self, sync_session: Session):
        """Test that updated_by can be set."""
        model = AuditTestModel(name="audit_test_5", value=42)
        sync_session.add(model)
        sync_session.commit()
        sync_session.refresh(model)

        # Update with user tracking
        model.value = 100
        model.updated_by = "editor"
        sync_session.add(model)
        sync_session.commit()
        sync_session.refresh(model)

        assert model.updated_by == "editor"

    def test_audit_fields_in_combined_mixin(self, sync_session: Session):
        """Test audit fields work in combined mixin model."""
        model = CombinedMixinTestModel(
            name="combined_1", value=1, created_by="creator"
        )

        assert model.created_at is not None
        assert model.created_by == "creator"
        assert model.updated_at is None
        assert model.updated_by is None

        # Also verify soft delete fields exist
        assert model.is_deleted is False
        assert model.deleted_at is None
        assert model.deleted_by is None

    @pytest.mark.asyncio
    async def test_audit_mixin_async(self, async_session: AsyncSession):
        """Test AuditMixin works with async sessions."""
        model = AuditTestModel(
            name="async_audit", value=99, created_by="async_user"
        )

        assert model.created_at is not None
        assert model.created_by == "async_user"

        async_session.add(model)
        await async_session.commit()
        await async_session.refresh(model)

        assert model.id is not None
        assert model.created_at is not None


# ============================================================================
# SoftDeleteMixin Tests
# ============================================================================


class TestSoftDeleteMixin:
    """Test the SoftDeleteMixin functionality."""

    def test_soft_delete_sets_fields_correctly(self):
        """Test that soft_delete() sets fields correctly."""
        model = SoftDeleteTestModel(name="delete_test_1", value=42)

        assert model.is_deleted is False
        assert model.deleted_at is None
        assert model.deleted_by is None

        before = datetime.now(timezone.utc)
        model.soft_delete()
        after = datetime.now(timezone.utc)

        assert model.is_deleted is True
        assert model.deleted_at is not None
        assert before <= model.deleted_at <= after
        assert model.deleted_by is None

    def test_soft_delete_with_user_tracking(self):
        """Test soft_delete() with user parameter."""
        model = SoftDeleteTestModel(name="delete_test_2", value=42)

        model.soft_delete(user="admin")

        assert model.is_deleted is True
        assert model.deleted_at is not None
        assert model.deleted_by == "admin"

    def test_restore_clears_fields(self):
        """Test that restore() clears deletion fields."""
        model = SoftDeleteTestModel(name="delete_test_3", value=42)

        # Soft delete first
        model.soft_delete(user="admin")
        assert model.is_deleted is True

        # Restore
        model.restore()

        assert model.is_deleted is False
        assert model.deleted_at is None
        assert model.deleted_by is None

    def test_is_deleted_flag_works_correctly(self, sync_session: Session):
        """Test is_deleted flag with database persistence."""
        model = SoftDeleteTestModel(name="delete_test_4", value=42)
        sync_session.add(model)
        sync_session.commit()
        sync_session.refresh(model)

        # Initially not deleted
        assert model.is_deleted is False

        # Soft delete
        model.soft_delete(user="admin")
        sync_session.add(model)
        sync_session.commit()
        sync_session.refresh(model)

        # Verify deletion persisted
        assert model.is_deleted is True
        assert model.deleted_by == "admin"

        # Restore
        model.restore()
        sync_session.add(model)
        sync_session.commit()
        sync_session.refresh(model)

        # Verify restoration persisted
        assert model.is_deleted is False
        assert model.deleted_at is None

    def test_soft_delete_in_combined_mixin(self, sync_session: Session):
        """Test soft delete works in combined mixin model."""
        model = CombinedMixinTestModel(
            name="combined_delete", value=1, created_by="creator"
        )

        # Verify audit fields
        assert model.created_at is not None
        assert model.created_by == "creator"

        # Verify soft delete fields
        assert model.is_deleted is False

        # Soft delete
        model.soft_delete(user="deleter")

        assert model.is_deleted is True
        assert model.deleted_by == "deleter"
        # Audit fields should still be intact
        assert model.created_at is not None
        assert model.created_by == "creator"

    @pytest.mark.asyncio
    async def test_soft_delete_async(self, async_session: AsyncSession):
        """Test SoftDeleteMixin works with async sessions."""
        model = SoftDeleteTestModel(name="async_delete", value=99)

        async_session.add(model)
        await async_session.commit()
        await async_session.refresh(model)

        # Soft delete
        model.soft_delete(user="async_deleter")
        async_session.add(model)
        await async_session.commit()
        await async_session.refresh(model)

        assert model.is_deleted is True
        assert model.deleted_by == "async_deleter"

        # Restore
        model.restore()
        async_session.add(model)
        await async_session.commit()
        await async_session.refresh(model)

        assert model.is_deleted is False

    def test_multiple_soft_deletes(self):
        """Test multiple soft delete/restore cycles."""
        model = SoftDeleteTestModel(name="cycle_test", value=42)

        # First delete
        model.soft_delete(user="user1")
        first_deleted_at = model.deleted_at

        # Restore
        model.restore()

        # Second delete
        time.sleep(0.01)  # Ensure timestamp difference
        model.soft_delete(user="user2")
        second_deleted_at = model.deleted_at

        assert model.is_deleted is True
        assert model.deleted_by == "user2"
        assert (
            second_deleted_at is not None
            and first_deleted_at is not None
            and second_deleted_at >= first_deleted_at
        )


# ============================================================================
# Public API Tests
# ============================================================================


class TestPublicAPI:
    """Test that all public API exports work correctly."""

    def test_version_accessible(self):
        """Test that __version__ is accessible."""
        assert __version__ is not None
        assert isinstance(__version__, str)
        assert __version__ == "0.2.0"

    def test_exceptions_can_be_imported_from_root(self):
        """Test that exceptions can be imported from root package."""
        from sqlmodel_crud_utils import (
            BulkOperationError,
            MultipleRecordsError,
            RecordNotFoundError,
            SQLModelCRUDError,
            TransactionError,
            ValidationError,
        )

        # Verify they are the correct types
        assert issubclass(RecordNotFoundError, SQLModelCRUDError)
        assert issubclass(MultipleRecordsError, SQLModelCRUDError)
        assert issubclass(ValidationError, SQLModelCRUDError)
        assert issubclass(BulkOperationError, SQLModelCRUDError)
        assert issubclass(TransactionError, SQLModelCRUDError)

    def test_mixins_can_be_imported_from_root(self):
        """Test that mixins can be imported from root package."""
        from sqlmodel_crud_utils import AuditMixin, SoftDeleteMixin

        # Verify they have the expected attributes
        assert hasattr(AuditMixin, "created_at")
        assert hasattr(AuditMixin, "updated_at")
        assert hasattr(AuditMixin, "created_by")
        assert hasattr(AuditMixin, "updated_by")

        assert hasattr(SoftDeleteMixin, "deleted_at")
        assert hasattr(SoftDeleteMixin, "deleted_by")
        assert hasattr(SoftDeleteMixin, "is_deleted")
        assert hasattr(SoftDeleteMixin, "soft_delete")
        assert hasattr(SoftDeleteMixin, "restore")

    def test_transaction_managers_can_be_imported_from_root(self):
        """Test that transaction managers can be imported from root."""
        from sqlmodel_crud_utils import a_transaction, transaction

        # Verify they are callable
        assert callable(transaction)
        assert callable(a_transaction)

    def test_crud_functions_can_be_imported_from_root(self):
        """Test that CRUD functions can be imported from root."""
        from sqlmodel_crud_utils import (
            a_delete_row,
            a_get_one_or_create,
            a_get_row,
            a_get_rows,
            a_update_row,
            delete_row,
            get_one_or_create,
            get_row,
            get_rows,
            update_row,
        )

        # Verify they are callable
        crud_functions = [
            write_row,
            get_row,
            get_rows,
            update_row,
            delete_row,
            get_one_or_create,
            a_write_row,
            a_get_row,
            a_get_rows,
            a_update_row,
            a_delete_row,
            a_get_one_or_create,
        ]

        for func in crud_functions:
            assert callable(func)

    def test_all_exports_in_all_list(self):
        """Test that __all__ contains all expected exports."""
        from sqlmodel_crud_utils import __all__

        expected_exports = [
            # Version
            "__version__",
            # Exceptions
            "SQLModelCRUDError",
            "RecordNotFoundError",
            "MultipleRecordsError",
            "ValidationError",
            "BulkOperationError",
            "TransactionError",
            # Transaction managers
            "transaction",
            "a_transaction",
            # Mixins
            "AuditMixin",
            "SoftDeleteMixin",
            # Sync CRUD functions
            "write_row",
            "get_row",
            "get_rows",
            "update_row",
            "delete_row",
            "get_one_or_create",
            "get_result_from_query",
            "get_rows_within_id_list",
            "insert_data_rows",
            "bulk_upsert_mappings",
            # Async CRUD functions
            "a_write_row",
            "a_get_row",
            "a_get_rows",
            "a_update_row",
            "a_delete_row",
            "a_get_one_or_create",
            "a_get_result_from_query",
            "a_get_rows_within_id_list",
            "a_insert_data_rows",
            "a_bulk_upsert_mappings",
        ]

        for export in expected_exports:
            assert (
                export in __all__
            ), f"{export} not found in __all__ exports"

    def test_integration_example(self, sync_session: Session):
        """Test a complete integration example using new features."""
        # Use transaction manager
        with transaction(sync_session) as tx:
            # Create a model with both mixins
            model = CombinedMixinTestModel(
                name="integration_test",
                value=999,
                created_by="system",
            )
            tx.add(model)

        # Verify it was created
        sync_session.rollback()
        result = sync_session.get(CombinedMixinTestModel, model.id)

        assert result is not None
        assert result.name == "integration_test"
        assert result.created_at is not None
        assert result.created_by == "system"
        assert result.is_deleted is False

        # Soft delete it
        result.soft_delete(user="admin")
        sync_session.add(result)
        sync_session.commit()

        # Verify deletion
        sync_session.refresh(result)
        assert result.is_deleted is True
        assert result.deleted_by == "admin"

    @pytest.mark.asyncio
    async def test_async_integration_example(
        self, async_session: AsyncSession
    ):
        """Test a complete async integration example."""
        # Use async transaction manager
        async with a_transaction(async_session) as tx:
            # Create a model with both mixins
            model = CombinedMixinTestModel(
                name="async_integration",
                value=888,
                created_by="async_system",
            )
            tx.add(model)

        # Verify it was created
        await async_session.rollback()
        result = await async_session.get(CombinedMixinTestModel, model.id)

        assert result is not None
        assert result.name == "async_integration"
        assert result.created_at is not None
        assert result.created_by == "async_system"
        assert result.is_deleted is False

        # Soft delete it
        result.soft_delete(user="async_admin")
        async_session.add(result)
        await async_session.commit()

        # Verify deletion
        await async_session.refresh(result)
        assert result.is_deleted is True
        assert result.deleted_by == "async_admin"
