"""Mixins for common database patterns.

This module provides reusable mixins for SQLModel models to add common
functionality like audit trails and soft delete support.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field


def _utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


class AuditMixin:
    """Mixin for automatic audit trail tracking.

    Adds timestamp fields to track when records are created and updated,
    along with optional user tracking fields.

    Attributes:
        created_at: Timestamp when the record was created (auto-set)
        updated_at: Timestamp when the record was last updated
            (auto-set on update)
        created_by: Optional username/ID of creator
        updated_by: Optional username/ID of last updater

    Example:
        Basic usage:

        >>> from sqlmodel import SQLModel, Field
        >>> from sqlmodel_crud_utils.mixins import AuditMixin
        >>>
        >>> class User(SQLModel, AuditMixin, table=True):
        ...     id: Optional[int] = Field(default=None, primary_key=True)
        ...     name: str
        ...     email: str
        >>>
        >>> # When you create a User, created_at is automatically set
        >>> user = User(name="Alice", email="alice@example.com")
        >>> # user.created_at will be set to current UTC time

        With user tracking:

        >>> user = User(
        ...     name="Bob",
        ...     email="bob@example.com",
        ...     created_by="admin"
        ... )
        >>> # Later when updating
        >>> user.name = "Robert"
        >>> user.updated_by = "admin"
        >>> # updated_at will be automatically set on commit

    Note:
        The `updated_at` field uses SQLAlchemy's `onupdate` parameter to
        automatically update the timestamp when the record is modified.
    """

    created_at: datetime = Field(
        default_factory=_utc_now,
        nullable=False,
        index=True,
        description="Timestamp when the record was created",
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        sa_column_kwargs={"onupdate": _utc_now},
        description="Timestamp when the record was last updated",
    )
    created_by: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Username or ID of the user who created this record",
    )
    updated_by: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Username or ID of the user who last updated this record",
    )


class SoftDeleteMixin:
    """Mixin for soft delete functionality.

    Adds fields and methods to support soft deletion, where records are marked
    as deleted but not actually removed from the database. This allows for
    recovery and maintains referential integrity.

    Attributes:
        deleted_at: Timestamp when the record was soft-deleted
        deleted_by: Optional username/ID of user who deleted the record
        is_deleted: Boolean flag indicating if record is deleted

    Methods:
        soft_delete: Mark the record as deleted
        restore: Restore a soft-deleted record

    Example:
        Basic usage:

        >>> from sqlmodel import SQLModel, Field
        >>> from sqlmodel_crud_utils.mixins import SoftDeleteMixin
        >>>
        >>> class Product(SQLModel, SoftDeleteMixin, table=True):
        ...     id: Optional[int] = Field(default=None, primary_key=True)
        ...     name: str
        ...     price: float
        >>>
        >>> product = Product(name="Widget", price=9.99)
        >>> # Later, soft delete it
        >>> product.soft_delete(user="admin")
        >>> # product.is_deleted is now True
        >>> # product.deleted_at is set to current time
        >>> # product.deleted_by is "admin"

        Restoring a deleted record:

        >>> product.restore()
        >>> # product.is_deleted is now False
        >>> # product.deleted_at is None
        >>> # product.deleted_by is None

        Combining with AuditMixin:

        >>> class Order(SQLModel, AuditMixin, SoftDeleteMixin, table=True):
        ...     id: Optional[int] = Field(default=None, primary_key=True)
        ...     total: float
        >>>
        >>> # Now Order has both audit trail and soft delete support

    Note:
        When querying, you'll typically want to filter out soft-deleted records:
        `select(Product).where(Product.is_deleted == False)`

        The `get_rows` function in this library can be extended to automatically
        exclude soft-deleted records by default.
    """

    deleted_at: Optional[datetime] = Field(
        default=None,
        index=True,
        description="Timestamp when the record was soft-deleted",
    )
    deleted_by: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Username or ID of the user who deleted this record",
    )
    is_deleted: bool = Field(
        default=False,
        index=True,
        description="Flag indicating if the record is soft-deleted",
    )

    def soft_delete(self, user: Optional[str] = None) -> None:
        """Mark this record as deleted.

        Sets the is_deleted flag to True, records the deletion
        timestamp, and optionally tracks which user performed the
        deletion.

        Args:
            user: Optional username or user ID of the person
                performing the deletion

        Example:
            >>> product.soft_delete(user="admin")
            >>> assert product.is_deleted is True
            >>> assert product.deleted_at is not None
            >>> assert product.deleted_by == "admin"

        Note:
            This method only modifies the object in memory. You must still
            commit the session to persist the changes to the database.
        """
        self.is_deleted = True
        self.deleted_at = _utc_now()
        self.deleted_by = user

    def restore(self) -> None:
        """Restore a soft-deleted record.

        Clears the deletion flag and resets all deletion-related fields
        to their default values.

        Example:
            >>> product.restore()
            >>> assert product.is_deleted is False
            >>> assert product.deleted_at is None
            >>> assert product.deleted_by is None

        Note:
            This method only modifies the object in memory. You must still
            commit the session to persist the changes to the database.
        """
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by = None
