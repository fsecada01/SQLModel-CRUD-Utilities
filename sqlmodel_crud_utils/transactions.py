"""Transaction context managers for safe database operations.

This module provides context managers for handling database transactions with
automatic commit and rollback functionality. These utilities ensure that
database operations are properly committed on success or rolled back on error.
"""

from contextlib import asynccontextmanager, contextmanager
from typing import AsyncGenerator, Generator

from sqlmodel import Session
from sqlmodel.ext.asyncio.session import AsyncSession

from .exceptions import TransactionError


@contextmanager
def transaction(session: Session) -> Generator[Session, None, None]:
    """Context manager for synchronous database transactions.

    Automatically commits the transaction on successful completion or
    rolls back on any exception. The original exception is wrapped in a
    TransactionError to provide additional context while preserving the
    exception chain.

    Args:
        session: An active SQLModel Session instance

    Yields:
        Session: The same session instance for use within the context

    Raises:
        TransactionError: Wraps any exception that occurs during
            the transaction, with the original exception available
            via __cause__

    Example:
        Basic usage with automatic commit:

        >>> from sqlmodel import Session, create_engine
        >>> from sqlmodel_crud_utils import write_row, update_row
        >>> from sqlmodel_crud_utils.transactions import transaction
        >>>
        >>> engine = create_engine("sqlite:///database.db")
        >>> with Session(engine) as session:
        ...     with transaction(session) as tx:
        ...         user = write_row(User(name="Alice"), tx)
        ...         update_row(
        ...             user.id, {"email": "alice@example.com"}, User, tx
        ...         )
        ...         # Automatically commits here if no exceptions

        Error handling with automatic rollback:

        >>> from sqlmodel import Session
        >>> from sqlmodel_crud_utils.transactions import transaction
        >>> from sqlmodel_crud_utils.exceptions import TransactionError
        >>>
        >>> with Session(engine) as session:
        ...     try:
        ...         with transaction(session) as tx:
        ...             user = write_row(User(name="Bob"), tx)
        ...             # Some operation that fails
        ...             raise ValueError("Invalid email format")
        ...     except TransactionError as e:
        ...         print(f"Transaction failed: {e}")
        ...         print(f"Original error: {e.__cause__}")
        ...         # Database automatically rolled back

        Multiple operations in a single transaction:

        >>> with Session(engine) as session:
        ...     with transaction(session) as tx:
        ...         # All operations succeed together or all are rolled back
        ...         user = write_row(User(name="Charlie"), tx)
        ...         profile = write_row(Profile(user_id=user.id), tx)
        ...         update_row(user.id, {"active": True}, User, tx)

    Notes:
        - The session is committed only if no exceptions occur
        - Any exception triggers an automatic rollback before re-raising
        - The session remains usable after the context exits
        - Nested transactions are not supported; use savepoints instead
        - The session must not be in an existing transaction when entering
    """
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        raise TransactionError(f"Transaction failed: {e}") from e


@asynccontextmanager
async def a_transaction(
    session: AsyncSession,
) -> AsyncGenerator[AsyncSession, None]:
    """Context manager for asynchronous database transactions.

    Asynchronous version of the transaction() context manager. Provides
    the same automatic commit/rollback behavior for async database
    operations.

    Args:
        session: An active AsyncSession instance from
            sqlmodel.ext.asyncio.session

    Yields:
        AsyncSession: The same session instance for use within the
            async context

    Raises:
        TransactionError: Wraps any exception that occurs during
            the transaction, with the original exception available
            via __cause__

    Example:
        Basic async usage with automatic commit:

        >>> from sqlmodel.ext.asyncio.session import AsyncSession
        >>> from sqlalchemy.ext.asyncio import create_async_engine
        >>> from sqlmodel_crud_utils import a_write_row, a_update_row
        >>> from sqlmodel_crud_utils.transactions import a_transaction
        >>>
        >>> engine = create_async_engine("sqlite+aiosqlite:///database.db")
        >>> async with AsyncSession(engine) as session:
        ...     async with a_transaction(session) as tx:
        ...         user = await a_write_row(
        ...             User(name="Alice"), tx
        ...         )
        ...         await a_update_row(
        ...             user.id, {"email": "alice@example.com"},
        ...             User, tx
        ...         )
        ...         # Automatically commits here if no exceptions

        Error handling with automatic rollback:

        >>> from sqlmodel.ext.asyncio.session import AsyncSession
        >>> from sqlmodel_crud_utils.transactions import a_transaction
        >>> from sqlmodel_crud_utils.exceptions import TransactionError
        >>>
        >>> async with AsyncSession(engine) as session:
        ...     try:
        ...         async with a_transaction(session) as tx:
        ...             user = await a_write_row(User(name="Bob"), tx)
        ...             # Some async operation that fails
        ...             raise ValueError("Invalid email format")
        ...     except TransactionError as e:
        ...         print(f"Transaction failed: {e}")
        ...         print(f"Original error: {e.__cause__}")
        ...         # Database automatically rolled back

        Multiple async operations in a single transaction:

        >>> async with AsyncSession(engine) as session:
        ...     async with a_transaction(session) as tx:
        ...         # All operations succeed together or all are rolled back
        ...         user = await a_write_row(User(name="Charlie"), tx)
        ...         profile = await a_write_row(Profile(user_id=user.id), tx)
        ...         await a_update_row(user.id, {"active": True}, User, tx)

        Using with FastAPI dependency injection:

        >>> from fastapi import Depends, FastAPI
        >>> from sqlmodel.ext.asyncio.session import AsyncSession
        >>> from sqlmodel_crud_utils.transactions import a_transaction
        >>>
        >>> app = FastAPI()
        >>>
        >>> async def get_session():
        ...     async with AsyncSession(engine) as session:
        ...         yield session
        >>>
        >>> @app.post("/users")
        >>> async def create_user(
        ...     user_data: dict,
        ...     session: AsyncSession = Depends(get_session)
        ... ):
        ...     async with a_transaction(session) as tx:
        ...         user = await a_write_row(User(**user_data), tx)
        ...         await a_write_row(AuditLog(action="user_created"), tx)
        ...         return user

    Notes:
        - The session is committed only if no exceptions occur
        - Any exception triggers an automatic rollback before re-raising
        - The session remains usable after the context exits
        - Nested transactions are not supported; use savepoints instead
        - The session must not be in an existing transaction when entering
        - Works seamlessly with asyncio, FastAPI, and other async frameworks
    """
    try:
        yield session
        await session.commit()
    except Exception as e:
        await session.rollback()
        raise TransactionError(f"Transaction failed: {e}") from e
