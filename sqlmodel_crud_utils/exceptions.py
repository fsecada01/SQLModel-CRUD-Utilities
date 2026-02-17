"""
Custom exception hierarchy for sqlmodel-crud-utils.

This module defines a comprehensive set of exceptions for better error handling
and debugging throughout the library. All exceptions inherit from the base
SQLModelCRUDError class.

Example:
    Basic exception handling:

    >>> from sqlmodel_crud_utils.exceptions import RecordNotFoundError
    >>> try:
    ...     success, user = get_row(id_str=999, session=session, model=User)
    ...     if not success:
    ...         raise RecordNotFoundError(model=User, id_value=999)
    ... except RecordNotFoundError as e:
    ...     print(f"User not found: {e}")

    Handling bulk operation errors:

    >>> from sqlmodel_crud_utils.exceptions import BulkOperationError
    >>> try:
    ...     process_bulk_data(data)
    ... except BulkOperationError as e:
    ...     print(f"Failed: {e.failed}/{e.total} records")
    ...     for error in e.errors:
    ...         print(f"  - {error}")
"""

from typing import Any


class SQLModelCRUDError(Exception):
    """
    Base exception for all sqlmodel-crud-utils errors.

    This is the root exception class for the library. All other exceptions
    inherit from this class, allowing users to catch all library-specific
    errors with a single except clause.

    Example:
        >>> try:
        ...     # Any library operation
        ...     pass
        ... except SQLModelCRUDError as e:
        ...     # Handle any library error
        ...     logger.error(f"CRUD operation failed: {e}")
    """

    pass


class RecordNotFoundError(SQLModelCRUDError):
    """
    Raised when a requested database record is not found.

    This exception is raised when attempting to retrieve, update, or delete
    a record that doesn't exist in the database. It stores contextual
    information about the model, ID value, and primary key field for
    better debugging.

    Attributes:
        model: The SQLModel class that was being queried.
        id_value: The primary key value that was searched for.
        pk_field: The name of the primary key field (default: "id").

    Example:
        >>> from models import User
        >>> raise RecordNotFoundError(
        ...     model=User,
        ...     id_value=123,
        ...     pk_field="user_id"
        ... )
        RecordNotFoundError: User with user_id=123 not found
    """

    def __init__(
        self,
        model: type,
        id_value: Any,
        pk_field: str = "id",
    ):
        """
        Initialize RecordNotFoundError.

        Args:
            model: The SQLModel class being queried.
            id_value: The primary key value that wasn't found.
            pk_field: Name of the primary key field (default: "id").
        """
        self.model = model
        self.id_value = id_value
        self.pk_field = pk_field

        # Create a helpful error message
        model_name = (
            model.__name__ if hasattr(model, "__name__") else str(model)
        )
        super().__init__(f"{model_name} with {pk_field}={id_value!r} not found")


class MultipleRecordsError(SQLModelCRUDError):
    """
    Raised when multiple records are found where exactly one was expected.

    This exception occurs when a query expected to return a single record
    returns multiple results instead. This typically indicates a data integrity
    issue or an incorrect query filter.

    Attributes:
        model: The SQLModel class that was being queried.
        count: The number of records found.
        filters: Optional dictionary of filters that were applied.

    Example:
        >>> from models import User
        >>> raise MultipleRecordsError(
        ...     model=User,
        ...     count=3,
        ...     filters={"email": "test@example.com"}
        ... )
        MultipleRecordsError: Expected 1 User, found 3
            (filters: {'email': 'test@example.com'})
    """

    def __init__(
        self,
        model: type,
        count: int,
        filters: dict[str, Any] | None = None,
    ):
        """
        Initialize MultipleRecordsError.

        Args:
            model: The SQLModel class being queried.
            count: Number of records found.
            filters: Optional dictionary of filters applied to the query.
        """
        self.model = model
        self.count = count
        self.filters = filters

        # Create error message
        model_name = (
            model.__name__ if hasattr(model, "__name__") else str(model)
        )
        message = f"Expected 1 {model_name}, found {count}"

        if filters:
            message += f" (filters: {filters})"

        super().__init__(message)


class ValidationError(SQLModelCRUDError):
    """
    Raised when data validation fails before or after a database operation.

    This exception is used for various validation failures, including:
    - Invalid field values
    - Missing required fields
    - Type mismatches
    - Business logic validation failures

    Attributes:
        field: Optional name of the field that failed validation.
        value: Optional value that failed validation.
        message: Detailed error message.
        errors: Optional dictionary mapping field names to error messages.

    Example:
        >>> raise ValidationError(
        ...     field="age",
        ...     value=-5,
        ...     message="Age must be a positive integer"
        ... )
        ValidationError: Validation failed for field 'age':
            Age must be a positive integer (value: -5)

        Multiple field errors:
        >>> raise ValidationError(
        ...     message="Multiple validation errors",
        ...     errors={
        ...         "email": "Invalid email format",
        ...         "age": "Must be 18 or older"
        ...     }
        ... )
    """

    def __init__(
        self,
        message: str,
        field: str | None = None,
        value: Any | None = None,
        errors: dict[str, str] | None = None,
    ):
        """
        Initialize ValidationError.

        Args:
            message: Detailed error message.
            field: Optional name of the field that failed.
            value: Optional value that caused the validation failure.
            errors: Optional dict mapping field names to error messages.
        """
        self.field = field
        self.value = value
        self.errors = errors

        # Build comprehensive error message
        if field:
            full_message = f"Validation failed for field '{field}': {message}"
            if value is not None:
                full_message += f" (value: {value!r})"
        else:
            full_message = f"Validation failed: {message}"

        if errors:
            error_details = "\n".join(
                f"  - {field}: {error}" for field, error in errors.items()
            )
            full_message += f"\n{error_details}"

        super().__init__(full_message)


class BulkOperationError(SQLModelCRUDError):
    """
    Raised when bulk database operations partially or completely fail.

    This exception is used when processing multiple records in a batch
    operation, and some or all of the records fail to process. It provides
    detailed information about the failure rate and individual errors.

    Attributes:
        total: Total number of records in the bulk operation.
        failed: Number of records that failed to process.
        errors: List of error messages or exception details for failed records.
        successful: Optional list of successfully processed record IDs.
        failed_records: Optional list of records that failed processing.

    Example:
        >>> raise BulkOperationError(
        ...     total=100,
        ...     failed=5,
        ...     errors=[
        ...         "Record 23: Duplicate key violation",
        ...         "Record 45: Invalid foreign key",
        ...         "Record 67: Missing required field",
        ...         "Record 89: Data too long for column",
        ...         "Record 91: Constraint violation"
        ...     ]
        ... )
        BulkOperationError: Bulk operation failed: 5/100 records failed
    """

    def __init__(
        self,
        total: int,
        failed: int,
        errors: list[str | Exception],
        successful: list[Any] | None = None,
        failed_records: list[Any] | None = None,
    ):
        """
        Initialize BulkOperationError.

        Args:
            total: Total number of records in the operation.
            failed: Number of records that failed.
            errors: List of error messages or exceptions for failures.
            successful: Optional list of successfully processed items.
            failed_records: Optional list of records that failed.
        """
        self.total = total
        self.failed = failed
        self.errors = errors
        self.successful = successful
        self.failed_records = failed_records

        # Calculate success rate for message
        success_rate = ((total - failed) / total * 100) if total > 0 else 0

        message = (
            f"Bulk operation failed: {failed}/{total} records failed "
            f"({success_rate:.1f}% success rate)"
        )

        super().__init__(message)

    def get_error_summary(self) -> str:
        """
        Get a formatted summary of all errors.

        Returns:
            A multi-line string with formatted error details.

        Example:
            >>> try:
            ...     bulk_operation()
            ... except BulkOperationError as e:
            ...     print(e.get_error_summary())
        """
        summary = [str(self)]
        summary.append("\nError details:")

        for i, error in enumerate(self.errors, 1):
            if isinstance(error, Exception):
                summary.append(f"  {i}. {type(error).__name__}: {error}")
            else:
                summary.append(f"  {i}. {error}")

        return "\n".join(summary)


class TransactionError(SQLModelCRUDError):
    """
    Raised when database transaction operations fail.

    This exception is used for transaction-related failures, including:
    - Failed commits
    - Rollback errors
    - Nested transaction issues
    - Deadlock scenarios
    - Connection issues during transaction

    Attributes:
        operation: The transaction operation that failed
            (e.g., "commit", "rollback").
        original_error: The underlying exception that caused the
            failure.

    Example:
        >>> try:
        ...     session.commit()
        ... except Exception as e:
        ...     raise TransactionError(
        ...         operation="commit",
        ...         original_error=e
        ...     )
        TransactionError: Transaction operation 'commit' failed:
            IntegrityError(...)
    """

    def __init__(
        self,
        message: str | None = None,
        operation: str | None = None,
        original_error: Exception | None = None,
    ):
        """
        Initialize TransactionError.

        Args:
            message: Optional custom error message.
            operation: The transaction operation that failed.
            original_error: The underlying exception that caused the failure.
        """
        self.operation = operation
        self.original_error = original_error

        # Build error message
        if message:
            full_message = message
        elif operation and original_error:
            error_name = type(original_error).__name__
            full_message = (
                f"Transaction operation '{operation}' failed: "
                f"{error_name}({original_error})"
            )
        elif operation:
            full_message = f"Transaction operation '{operation}' failed"
        elif original_error:
            full_message = f"Transaction failed: {original_error}"
        else:
            full_message = "Transaction operation failed"

        super().__init__(full_message)


class DatabaseConnectionError(SQLModelCRUDError):
    """
    Raised when database connection operations fail.

    This exception is used for connection-related failures, including:
    - Failed connection attempts
    - Connection timeout
    - Connection pool exhaustion
    - Authentication failures
    - Network issues

    Attributes:
        database_url: Optional sanitized database URL (without credentials).
        original_error: The underlying exception that caused the failure.

    Example:
        >>> raise DatabaseConnectionError(
        ...     database_url="postgresql://localhost:5432/mydb",
        ...     original_error=TimeoutError("Connection timeout")
        ... )
    """

    def __init__(
        self,
        message: str | None = None,
        database_url: str | None = None,
        original_error: Exception | None = None,
    ):
        """
        Initialize DatabaseConnectionError.

        Args:
            message: Optional custom error message.
            database_url: Optional database URL (credentials will be sanitized).
            original_error: The underlying exception that caused the failure.
        """
        self.database_url = database_url
        self.original_error = original_error

        # Build error message
        if message:
            full_message = message
        elif database_url and original_error:
            full_message = (
                f"Failed to connect to database at {database_url}: "
                f"{type(original_error).__name__}({original_error})"
            )
        elif database_url:
            full_message = f"Failed to connect to database at {database_url}"
        elif original_error:
            full_message = f"Database connection failed: {original_error}"
        else:
            full_message = "Database connection failed"

        super().__init__(full_message)


class QueryExecutionError(SQLModelCRUDError):
    """
    Raised when a database query fails to execute.

    This exception is used for various query execution failures that are
    not covered by more specific exceptions.

    Attributes:
        query: Optional string representation of the query that failed.
        original_error: The underlying exception that caused the failure.

    Example:
        >>> raise QueryExecutionError(
        ...     query="SELECT * FROM users WHERE ...",
        ...     original_error=ProgrammingError("Column does not exist")
        ... )
    """

    def __init__(
        self,
        message: str | None = None,
        query: str | None = None,
        original_error: Exception | None = None,
    ):
        """
        Initialize QueryExecutionError.

        Args:
            message: Optional custom error message.
            query: Optional string representation of the query.
            original_error: The underlying exception that caused the failure.
        """
        self.query = query
        self.original_error = original_error

        # Build error message
        if message:
            full_message = message
        elif query and original_error:
            full_message = (
                f"Query execution failed: "
                f"{type(original_error).__name__}({original_error})\n"
                f"Query: {query[:200]}"
                f"{'...' if len(query) > 200 else ''}"
            )
        elif query:
            full_message = (
                f"Query execution failed: {query[:200]}"
                f"{'...' if len(query) > 200 else ''}"
            )
        elif original_error:
            full_message = f"Query execution failed: {original_error}"
        else:
            full_message = "Query execution failed"

        super().__init__(full_message)


# Convenience function for creating exceptions
def not_found(
    model: type, id_value: Any, pk_field: str = "id"
) -> RecordNotFoundError:
    """
    Convenience function to create a RecordNotFoundError.

    Args:
        model: The SQLModel class being queried.
        id_value: The primary key value that wasn't found.
        pk_field: Name of the primary key field (default: "id").

    Returns:
        A configured RecordNotFoundError instance.

    Example:
        >>> raise not_found(User, 123, "user_id")
    """
    return RecordNotFoundError(
        model=model, id_value=id_value, pk_field=pk_field
    )


def multiple_found(
    model: type, count: int, filters: dict[str, Any] | None = None
) -> MultipleRecordsError:
    """
    Convenience function to create a MultipleRecordsError.

    Args:
        model: The SQLModel class being queried.
        count: Number of records found.
        filters: Optional dictionary of filters applied.

    Returns:
        A configured MultipleRecordsError instance.

    Example:
        >>> raise multiple_found(User, 3, {"email": "test@example.com"})
    """
    return MultipleRecordsError(model=model, count=count, filters=filters)


def validation_error(
    message: str,
    field: str | None = None,
    value: Any | None = None,
    errors: dict[str, str] | None = None,
) -> ValidationError:
    """
    Convenience function to create a ValidationError.

    Args:
        message: Detailed error message.
        field: Optional field name that failed validation.
        value: Optional value that failed validation.
        errors: Optional dict of field-to-error mappings.

    Returns:
        A configured ValidationError instance.

    Example:
        >>> raise validation_error(
        ...     "Invalid email", field="email", value="not-an-email"
        ... )
    """
    return ValidationError(
        message=message, field=field, value=value, errors=errors
    )


# Export all exception classes
__all__ = [
    "SQLModelCRUDError",
    "RecordNotFoundError",
    "MultipleRecordsError",
    "ValidationError",
    "BulkOperationError",
    "TransactionError",
    "DatabaseConnectionError",
    "QueryExecutionError",
    # Convenience functions
    "not_found",
    "multiple_found",
    "validation_error",
]
