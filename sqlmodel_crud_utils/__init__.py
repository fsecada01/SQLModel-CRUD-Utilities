"""
SQLModel CRUD Utilities

A set of CRUD utilities to expedite operations with SQLModel, providing both
synchronous and asynchronous support for common database operations.

New in v0.2.0:
    - Custom exception hierarchy for better error handling
    - Transaction context managers for safe operations
    - Audit trail mixins (created_at, updated_at tracking)
    - Soft delete support (is_deleted flag)
    - Public API exports for easier imports
"""

__version__ = "0.2.0"

# Import asynchronous functions with a_ prefix
from sqlmodel_crud_utils.a_sync import (
    bulk_upsert_mappings as a_bulk_upsert_mappings,
)
from sqlmodel_crud_utils.a_sync import delete_row as a_delete_row
from sqlmodel_crud_utils.a_sync import get_one_or_create as a_get_one_or_create
from sqlmodel_crud_utils.a_sync import (
    get_result_from_query as a_get_result_from_query,
)
from sqlmodel_crud_utils.a_sync import get_row as a_get_row
from sqlmodel_crud_utils.a_sync import get_rows as a_get_rows
from sqlmodel_crud_utils.a_sync import (
    get_rows_within_id_list as a_get_rows_within_id_list,
)
from sqlmodel_crud_utils.a_sync import insert_data_rows as a_insert_data_rows
from sqlmodel_crud_utils.a_sync import update_row as a_update_row
from sqlmodel_crud_utils.a_sync import write_row as a_write_row

# Import exceptions
from sqlmodel_crud_utils.exceptions import (
    BulkOperationError,
    MultipleRecordsError,
    RecordNotFoundError,
    SQLModelCRUDError,
    TransactionError,
    ValidationError,
)

# Import mixins
from sqlmodel_crud_utils.mixins import AuditMixin, SoftDeleteMixin

# Import synchronous functions
from sqlmodel_crud_utils.sync import (
    bulk_upsert_mappings,
    delete_row,
    get_one_or_create,
    get_result_from_query,
    get_row,
    get_rows,
    get_rows_within_id_list,
    insert_data_rows,
    update_row,
    write_row,
)

# Import transaction managers
from sqlmodel_crud_utils.transactions import a_transaction, transaction

__all__ = [
    # Version
    "__version__",
    # Synchronous functions
    "bulk_upsert_mappings",
    "delete_row",
    "get_one_or_create",
    "get_result_from_query",
    "get_row",
    "get_rows",
    "get_rows_within_id_list",
    "insert_data_rows",
    "update_row",
    "write_row",
    # Asynchronous functions
    "a_bulk_upsert_mappings",
    "a_delete_row",
    "a_get_one_or_create",
    "a_get_result_from_query",
    "a_get_row",
    "a_get_rows",
    "a_get_rows_within_id_list",
    "a_insert_data_rows",
    "a_update_row",
    "a_write_row",
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
]
