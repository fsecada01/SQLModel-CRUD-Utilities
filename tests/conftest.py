import os
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock  # Import AsyncMock

import factory
import pytest
import pytest_asyncio
from models import MockModel, MockRelatedModel
from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session as SQLModelSession  # Import SQLModel Session
from sqlmodel import SQLModel
from sqlmodel import create_engine as create_sqlmodel_engine
from sqlmodel.ext.asyncio.session import (
    AsyncSession as SQLModelAsyncSession,  # Import SQLModel AsyncSession
)

# Define types if you haven't already, using the SQLModel versions
SyncSessionType = SQLModelSession
AsyncSessionType = SQLModelAsyncSession


DATABASE_URL_BASE = "./test_db.sqlite"
SYNC_DATABASE_URL = f"sqlite:///{DATABASE_URL_BASE}"
ASYNC_DATABASE_URL = f"sqlite+aiosqlite:///{DATABASE_URL_BASE}"


# --- Database Initialization Fixture (Session Scoped) ---
@pytest.fixture(scope="session")
def initialize_database():
    """
    Ensures the database file is removed and tables are created only once per
    session. Uses a synchronous engine as create_all is synchronous.
    """
    print(f"\nUsing test database: {DATABASE_URL_BASE}")
    db_file = DATABASE_URL_BASE[2:]

    # Always remove the DB file at the start of the session
    if os.path.exists(db_file):
        print(f"Removing existing database file: {db_file}")
        os.remove(db_file)

    print("Creating database tables for the session...")
    # Use a temporary engine just for setup
    sync_engine_for_setup = create_sqlmodel_engine(
        SYNC_DATABASE_URL, echo=False
    )
    try:
        # Ensure models are loaded (they are in this file)
        SQLModel.metadata.create_all(sync_engine_for_setup)
        print("Database tables created successfully.")
    except Exception as e:
        print(f"Error creating database tables: {e}")
        raise  # Re-raise the exception to fail the setup
    finally:
        sync_engine_for_setup.dispose()
        print("Setup engine disposed.")

    yield  # Allow tests depending on this fixture to run

    # Optional: Cleanup after all session tests if needed
    # if os.path.exists(db_file):
    #     print(f"Removing database file after session: {db_file}")
    #     os.remove(db_file)


# --- Engine Fixtures (Session Scoped) ---
@pytest_asyncio.fixture(scope="session")
async def async_engine(
    initialize_database,
) -> AsyncGenerator[AsyncEngine, None]:
    """Provides an async engine, initialized once per session."""
    engine = create_async_engine(ASYNC_DATABASE_URL, echo=False)
    yield engine
    print("\nDisposing async engine...")
    await engine.dispose()
    print("Async engine disposed.")


@pytest.fixture(scope="session")
def sync_engine(initialize_database) -> Generator[Engine, None, None]:
    """Provides a sync engine, initialized once per session."""
    engine = create_engine(SYNC_DATABASE_URL, echo=False)
    yield engine
    print("\nDisposing sync engine...")
    engine.dispose()
    print("Sync engine disposed.")


# --- Session Factory Fixtures (Session Scoped) ---
@pytest.fixture(scope="session")
def async_session_factory(
    async_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSessionType]:
    """Provides an async session factory, configured once per session."""
    return async_sessionmaker(
        bind=async_engine,
        class_=AsyncSessionType,
        expire_on_commit=False,
    )


@pytest.fixture(scope="session")
def sync_session_factory(
    sync_engine: Engine,
) -> sessionmaker[SyncSessionType]:
    """Provides a sync session factory, configured once per session."""
    return sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=sync_engine,
        class_=SyncSessionType,
    )


# --- Session Fixtures (Function Scoped for Test Isolation) ---
@pytest_asyncio.fixture(scope="function")
async def async_session(
    async_session_factory: async_sessionmaker[AsyncSessionType],
) -> AsyncGenerator[AsyncSessionType, None]:
    """
    Provides a clean async session for each test function.
    Rolls back changes after the test.
    """
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.rollback()


@pytest.fixture(scope="function")
def sync_session(
    sync_session_factory: sessionmaker[SyncSessionType],
) -> Generator[SyncSessionType, None, None]:
    """
    Provides a clean sync session for each test function.
    Rolls back changes after the test.
    """
    with sync_session_factory() as session:
        try:
            yield session
        finally:
            session.rollback()


# ... other fixtures ...


@pytest.fixture(scope="function")
def mock_sync_session() -> MagicMock:
    """Provides a MagicMock simulating a synchronous SQLModel Session."""
    session_mock = MagicMock(
        spec=SyncSessionType
    )  # Use SQLModelSession for spec

    # --- Add the exec attribute ---
    mock_exec_result = MagicMock()
    mock_exec_result.one_or_none.return_value = None
    mock_exec_result.all.return_value = []
    mock_exec_result.scalars.return_value = mock_exec_result  # Chain .scalars()
    mock_exec_result.scalar_one_or_none.return_value = (
        None  # Add scalar_one_or_none if used
    )
    session_mock.exec = MagicMock(
        return_value=mock_exec_result
    )  # Make exec a mock
    # --- End of addition ---

    # Mock other methods as needed (add, commit, rollback, get, etc.)
    session_mock.add = MagicMock()
    session_mock.commit = MagicMock()
    session_mock.rollback = MagicMock()
    session_mock.refresh = MagicMock()
    session_mock.delete = MagicMock()
    session_mock.get = MagicMock(return_value=None)  # Default get returns None
    session_mock.scalars = MagicMock(
        return_value=mock_exec_result
    )  # Mock session.scalars directly too

    return session_mock


@pytest.fixture(scope="function")
async def mock_async_session() -> AsyncMock:
    """Provides an AsyncMock simulating an asynchronous SQLModel Session."""
    session_mock = AsyncMock(
        spec=AsyncSessionType
    )  # Use SQLModelAsyncSession for spec

    # --- Add the exec attribute (as an AsyncMock) ---
    mock_exec_result = (
        AsyncMock()
    )  # Result of exec should also be awaitable/async
    mock_exec_result.one_or_none = AsyncMock(return_value=None)
    mock_exec_result.all = AsyncMock(return_value=[])
    mock_exec_result.scalars = AsyncMock(
        return_value=mock_exec_result
    )  # Chain .scalars()
    mock_exec_result.scalar_one_or_none = AsyncMock(
        return_value=None
    )  # Add scalar_one_or_none
    session_mock.exec = AsyncMock(
        return_value=mock_exec_result
    )  # Make exec an AsyncMock
    # --- End of addition ---

    # Mock other awaitable methods
    session_mock.commit = AsyncMock()
    session_mock.rollback = AsyncMock()
    session_mock.refresh = AsyncMock()
    session_mock.add = MagicMock()  # add is not async
    session_mock.add_all = MagicMock()  # add_all is not async
    session_mock.delete = (
        AsyncMock()
    )  # delete is not async usually, but can be part of async flow
    session_mock.get = AsyncMock(return_value=None)  # Default get returns None
    session_mock.scalars = AsyncMock(
        return_value=mock_exec_result
    )  # Mock session.scalars directly too

    # Configure specific return values or side effects for tests needing them
    # Example: session_mock.exec.return_value.one_or_none.return_value =
    # some_mock_object

    return session_mock


# --- Environment Setup ---
@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    """Sets the SQL_DIALECT environment variable for the test session."""
    print("\nSetting SQL_DIALECT=sqlite for test session")
    os.environ["SQL_DIALECT"] = "sqlite"


# --- SQLModel Definitions ---


# --- Factory Boy Definitions ---
class MockRelatedModelFactory(factory.Factory):
    class Meta:
        model = MockRelatedModel

    related_name = factory.Faker("word")


class MockModelFactory(factory.Factory):
    class Meta:
        model = MockModel

    name = factory.Faker("name")
    value = factory.Faker("random_int", min=0, max=1000)
    # related_field_id will be set during population if needed by tests
