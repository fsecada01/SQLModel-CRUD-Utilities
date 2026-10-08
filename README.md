<div align="left" style="position: relative;">
<img src="https://raw.githubusercontent.com/PKief/vscode-material-icon-theme/ec559a9f6bfd399b82bb44393651661b08aaf7ba/icons/folder-markdown-open.svg" align="right" width="30%" style="margin: -20px 0 0 20px;">
<h1>SQLMODEL_CRUD_UTILS</h1>
<p align="left">
	<em>A set of CRUD (Create, Read, Update, Delete) utilities designed to
streamline and expedite common database operations when using SQLModel, offering both synchronous and asynchronous support.</em>
</p>
<p align="left">
	<a href="https://pypi.org/project/sqlmodel-crud-utils/"><img alt="PyPI - Version" src="https://img.shields.io/pypi/v/sqlmodel-crud-utils"></a>
	<a href="https://github.com/fsecada01/SQLModel-CRUD-Utilities/actions"><img alt="CI Status" src="https://github.com/fsecada01/SQLModel-CRUD-Utilities/workflows/CI/badge.svg"></a>
	<a href="https://github.com/fsecada01/SQLModel-CRUD-Utilities/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/badge/License-MIT-blue.svg"></a>
</p>
<p align="left">Built with the tools and technologies:</p>
<p align="left">
	<img src="https://img.shields.io/badge/Python-3776AB.svg?style=default&logo=Python&logoColor=white" alt="Python">
    <img src="https://img.shields.io/badge/SQLModel-488efc.svg?style=default&logo=Python&logoColor=white" alt="SQLModel">
    <img src="https://img.shields.io/badge/SQLAlchemy-D71F00.svg?style=default&logo=Python&logoColor=white" alt="SQLAlchemy">
    <img src="https://img.shields.io/badge/pytest-0A9EDC.svg?style=default&logo=pytest&logoColor=white" alt="pytest">
    <img src="https://img.shields.io/badge/uv-43ccAC.svg?style=default&logo=Python&logoColor=white" alt="uv">
</p>
</div>
<br clear="right">

##  Table of Contents

- [Overview](#-overview)
- [What's New in v0.2.0](#-whats-new-in-v020)
- [Features](#-features)
- [Project Structure](#-project-structure)
  - [Project Index](#-project-index)
- [Getting Started](#-getting-started)
  - [Prerequisites](#-prerequisites)
  - [Configuration](#-configuration)
  - [Installation](#-installation)
  - [Usage](#-usage)
  - [Testing](#-testing)
- [Project Roadmap](#-project-roadmap)
- [Contributing](#-contributing)
- [License](#-license)
- [Acknowledgments](#-acknowledgments)

---

##  Overview
`sqlmodel-crud-utils` provides a convenient layer on top of SQLModel and SQLAlchemy to simplify common database interactions. It offers both synchronous and asynchronous functions for creating, reading, updating, and deleting data, along with helpers for bulk operations, filtering, pagination, and relationship loading. The goal is to reduce boilerplate code in projects using SQLModel.

---

##  What's New in v0.2.0

Version 0.2.0 brings significant enhancements focused on developer experience and production-ready features:

### Public API Exports
No more deep imports! All functions are now available directly from the package:
```python
# Before (v0.1.0)
from sqlmodel_crud_utils.sync import get_row, update_row
from sqlmodel_crud_utils.a_sync import get_row as a_get_row

# After (v0.2.0)
from sqlmodel_crud_utils import get_row, update_row, a_get_row
```

### Custom Exception Hierarchy
Better error handling with detailed, context-aware exceptions:
- `RecordNotFoundError` - When a record doesn't exist
- `MultipleRecordsError` - When one record expected but multiple found
- `ValidationError` - For data validation failures
- `BulkOperationError` - For bulk operation failures with detailed stats
- `TransactionError` - For transaction-related issues

### Transaction Context Managers
Safer database operations with automatic commit and rollback:
```python
from sqlmodel_crud_utils import transaction, write_row, update_row

with transaction(session) as tx:
    user = write_row(User(name="Alice"), tx)
    update_row(user.id, {"email": "alice@example.com"}, User, tx)
    # Automatically commits on success, rolls back on error
```

### Audit Trail Mixins
Automatic timestamp tracking for record creation and updates:
```python
from sqlmodel_crud_utils import AuditMixin

class User(SQLModel, AuditMixin, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    # Automatically adds: created_at, updated_at, created_by, updated_by
```

### Soft Delete Support
Mark records as deleted without actually removing them:
```python
from sqlmodel_crud_utils import SoftDeleteMixin

class Product(SQLModel, SoftDeleteMixin, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    # Automatically adds: is_deleted, deleted_at, deleted_by

product.soft_delete(user="admin")  # Mark as deleted
product.restore()                  # Restore it
```

**100% Backward Compatible** - All v0.1.0 code continues to work without changes!

---

##  Features

-   **Sync & Async Support:** Provides parallel functions in `sqlmodel_crud_utils.sync` and `sqlmodel_crud_utils.a_sync`.
-   **Public API Exports:** Simple imports from the main package with `a_` prefix for async functions.
-   **Simplified CRUD:** Offers high-level functions:
    - `get_one_or_create`: Retrieves an existing record or creates a new one.
    -   `get_row`: Fetches a single row by primary key.
    -   `get_rows`: Fetches multiple rows with flexible filtering, sorting, and pagination.
    -   `get_rows_within_id_list`: Fetches rows matching a list of primary keys.
    -   `update_row`: Updates fields of an existing row.
    -   `delete_row`: Deletes a row by primary key.
    -   `write_row`: Inserts a single new row.
    -   `insert_data_rows`: Inserts multiple new rows with fallback for individual insertion on bulk failure.
    -   `bulk_upsert_mappings`: Performs bulk insert-or-update operations (dialect-aware).
-   **Custom Exception Hierarchy:** Detailed exceptions for better error handling and debugging.
-   **Transaction Context Managers:** Safe transaction handling with automatic commit/rollback.
-   **Audit Trail Mixins:** Automatic timestamp and user tracking (`AuditMixin`).
-   **Soft Delete Support:** Mark records as deleted without removing them (`SoftDeleteMixin`).
-   **Relationship Loading:** Supports eager loading (`selectinload`) and lazy loading (`lazyload`) via parameters in `get_row` and `get_rows`.
-   **Flexible Filtering:** `get_rows` supports filtering by exact matches (`filter_by`) and common comparisons (`__like`, `__gte`, `__lte`, `__gt`, `__lt`, `__in`) using keyword arguments.
-   **Pagination:** Built-in pagination for `get_rows`.
-   **Dialect-Specific Upsert:** Automatically uses the correct `upsert` syntax (e.g., `ON CONFLICT DO UPDATE` for PostgreSQL/SQLite) based on the `SQL_DIALECT` environment variable.
-   **Type-Safe:** Full type hints for excellent IDE support and type checking.

---

##  Project Structure

```sh
└── sqlmodel_crud_utils/
    ├── __init__.py          # Public API exports
    ├── a_sync.py            # Asynchronous CRUD functions
    ├── sync.py              # Synchronous CRUD functions
    ├── utils.py             # Shared utilities
    ├── exceptions.py        # Custom exception hierarchy
    ├── transactions.py      # Transaction context managers
    └── mixins.py            # Audit and soft-delete mixins
```

###  Project Index
<details open>
	<summary><b><code>sqlmodel_crud_utils/</code></b></summary>
	<details> <!-- __root__ Submodule -->
		<summary><b>__root__</b></summary>
		<blockquote>
			<table>
			<tr>
				<td><b><a href='sqlmodel_crud_utils/blob/master/__init__.py'>__init__.py</a></b></td>
				<td>Public API exports for easy importing of all CRUD functions, exceptions, mixins, and transaction managers.</td>
			</tr>
			<tr>
				<td><b><a href='sqlmodel_crud_utils/blob/master/a_sync.py'>a_sync.py</a></b></td>
				<td>Contains asynchronous versions of the CRUD utility functions, designed for use with `asyncio` and async database drivers (e.g., `aiosqlite`, `asyncpg`).</td>
			</tr>
			<tr>
				<td><b><a href='sqlmodel_crud_utils/blob/master/sync.py'>sync.py</a></b></td>
				<td>Contains synchronous versions of the CRUD utility functions for standard execution environments.</td>
			</tr>
			<tr>
				<td><b><a href='sqlmodel_crud_utils/blob/master/utils.py'>utils.py</a></b></td>
				<td>Provides shared helper functions used by both `sync.py` and `a_sync.py`, such as environment variable retrieval and dynamic dialect-specific import logic for upsert statements.</td>
			</tr>
			<tr>
				<td><b><a href='sqlmodel_crud_utils/blob/master/exceptions.py'>exceptions.py</a></b></td>
				<td>Custom exception hierarchy for better error handling including RecordNotFoundError, ValidationError, BulkOperationError, and TransactionError.</td>
			</tr>
			<tr>
				<td><b><a href='sqlmodel_crud_utils/blob/master/transactions.py'>transactions.py</a></b></td>
				<td>Transaction context managers for safe database operations with automatic commit and rollback functionality.</td>
			</tr>
			<tr>
				<td><b><a href='sqlmodel_crud_utils/blob/master/mixins.py'>mixins.py</a></b></td>
				<td>Reusable mixins for common patterns like audit trails (AuditMixin) and soft deletes (SoftDeleteMixin).</td>
			</tr>
			</table>
		</blockquote>
	</details>
</details>

---

##  Getting Started

###  Prerequisites

-   **Python:** Version 3.9+ required.
-   **Database:** A SQLAlchemy-compatible database (e.g., PostgreSQL, SQLite, MySQL).
-   **SQLModel:** Your project should be using SQLModel for ORM definitions.

###  Configuration

This package requires the `SQL_DIALECT` environment variable to be set for the `upsert` functionality to work correctly across different database backends.

Set it in your environment:
```bash
export SQL_DIALECT=postgresql # or sqlite, mysql, etc
```

Or add it to a `.env` file in your project root (will be loaded automatically via `python-dotenv`):

```.env
SQL_DIALECT=postgresql
```

Refer to [SQLAlchemy Dialects](https://docs.sqlalchemy.org/en/20/dialects/) for a list of supported dialect names.

###  Installation

**Install from PyPI (Recommended):**
```bash
pip install sqlmodel-crud-utils
# Or using uv:
uv pip install sqlmodel-crud-utils
```

**Build from source:**

1. Clone the sqlmodel_crud_utils repository:
```sh
git clone https://github.com/fsecada01/SQLModel-CRUD-Utilities.git
```

2. Navigate to the project directory:
```sh
cd sqlmodel_crud_utils
```

3. Install the project dependencies:

```bash
uv pip install -r core_requirements.txt
# For testing/development
uv pip install -r dev_requirements.txt
```
*(Alternatively, use `pip install -r requirements.txt && pip install .`)*

###  Usage

Import the desired functions from the main package and use them with your SQLModel session and models.

#### Basic CRUD Operations (Synchronous)

```python
from sqlmodel import Session, SQLModel, create_engine, Field
from sqlmodel_crud_utils import get_one_or_create, get_rows, write_row, update_row

# Define your model
class MyModel(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    value: int | None = None

DATABASE_URL = "sqlite:///./mydatabase.db"
engine = create_engine(DATABASE_URL)
SQLModel.metadata.create_all(engine)

with Session(engine) as session:
    # Get or create an instance
    instance, created = get_one_or_create(
        session_inst=session,
        model=MyModel,
        name="Test Item",
        create_method_kwargs={"value": 123}
    )
    print(f"Instance ID: {instance.id}, Was created: {not created}")

    # Get rows matching criteria
    success, rows = get_rows(
        session_inst=session,
        model=MyModel,
        value__gte=100,
        sort_field="name"
    )
    if success:
        print(f"Found {len(rows)} rows with value >= 100:")
        for row in rows:
            print(f"- {row.name} (ID: {row.id})")
```

#### Using Public API Imports

```python
# Import everything you need from the main package
from sqlmodel_crud_utils import (
    # Sync functions
    get_row, get_rows, write_row, update_row, delete_row,
    # Async functions (with a_ prefix)
    a_get_row, a_get_rows, a_write_row, a_update_row,
    # Exceptions
    RecordNotFoundError, ValidationError,
    # Transaction managers
    transaction, a_transaction,
    # Mixins
    AuditMixin, SoftDeleteMixin
)
```

#### Exception Handling

```python
from sqlmodel_crud_utils import get_row, RecordNotFoundError

try:
    success, user = get_row(id_str=999, session_inst=session, model=User)
    if not success:
        raise RecordNotFoundError(model=User, id_value=999)
except RecordNotFoundError as e:
    print(f"Error: {e}")  # User with id=999 not found
    print(f"Model: {e.model.__name__}")  # Access exception details
    print(f"ID: {e.id_value}")
```

#### Transaction Context Managers

**Synchronous:**
```python
from sqlmodel_crud_utils import transaction, write_row, update_row

with Session(engine) as session:
    try:
        with transaction(session) as tx:
            # All operations succeed together or all are rolled back
            user = write_row(User(name="Alice", email="alice@example.com"), tx)
            profile = write_row(Profile(user_id=user.id, bio="Developer"), tx)
            update_row(user.id, {"verified": True}, User, tx)
            # Automatically commits here if no exceptions
    except TransactionError as e:
        print(f"Transaction failed: {e}")
        # Automatically rolled back
```

**Asynchronous:**
```python
from sqlmodel_crud_utils import a_transaction, a_write_row, a_update_row
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine

async_engine = create_async_engine("sqlite+aiosqlite:///./mydatabase.db")

async with AsyncSession(async_engine) as session:
    try:
        async with a_transaction(session) as tx:
            user = await a_write_row(User(name="Bob"), tx)
            await a_update_row(user.id, {"email": "bob@example.com"}, User, tx)
            # Automatically commits here if no exceptions
    except TransactionError as e:
        print(f"Transaction failed: {e}")
        # Automatically rolled back
```

#### Using AuditMixin

```python
from datetime import datetime
from sqlmodel import SQLModel, Field
from sqlmodel_crud_utils import AuditMixin, write_row

class User(SQLModel, AuditMixin, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    email: str
    # AuditMixin automatically adds:
    # - created_at: datetime
    # - updated_at: datetime | None
    # - created_by: str | None
    # - updated_by: str | None

with Session(engine) as session:
    # Create user with audit tracking
    user = User(name="Alice", email="alice@example.com", created_by="admin")
    user = write_row(user, session)

    # created_at is automatically set to current UTC time
    print(f"User created at: {user.created_at}")

    # When updating
    user.email = "alice.new@example.com"
    user.updated_by = "admin"
    session.add(user)
    session.commit()
    session.refresh(user)

    # updated_at is automatically updated
    print(f"User updated at: {user.updated_at}")
```

#### Using SoftDeleteMixin

```python
from sqlmodel import SQLModel, Field
from sqlmodel_crud_utils import SoftDeleteMixin, get_rows

class Product(SQLModel, SoftDeleteMixin, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    price: float
    # SoftDeleteMixin automatically adds:
    # - is_deleted: bool
    # - deleted_at: datetime | None
    # - deleted_by: str | None

with Session(engine) as session:
    # Create product
    product = Product(name="Widget", price=9.99)
    product = write_row(product, session)

    # Soft delete the product
    product.soft_delete(user="admin")
    session.add(product)
    session.commit()

    print(f"Deleted: {product.is_deleted}")  # True
    print(f"Deleted at: {product.deleted_at}")
    print(f"Deleted by: {product.deleted_by}")  # admin

    # Restore the product
    product.restore()
    session.add(product)
    session.commit()

    print(f"Deleted: {product.is_deleted}")  # False

    # Query non-deleted products
    from sqlmodel import select
    success, products = get_rows(
        session_inst=session,
        model=Product,
        is_deleted=False  # Filter out soft-deleted records
    )
```

#### Combining Mixins

```python
class Order(SQLModel, AuditMixin, SoftDeleteMixin, table=True):
    id: int | None = Field(default=None, primary_key=True)
    customer_id: int
    total: float
    # Now has both audit trail AND soft delete support!

with Session(engine) as session:
    order = Order(customer_id=1, total=99.99, created_by="system")
    order = write_row(order, session)

    # Track creation
    print(f"Order created at {order.created_at} by {order.created_by}")

    # Soft delete with tracking
    order.soft_delete(user="admin")
    session.commit()

    print(f"Order deleted at {order.deleted_at} by {order.deleted_by}")
```

###  Testing

Ensure development dependencies are installed (`uv pip install -r dev_requirements.txt` or `pip install -r dev_requirements.txt`).

Run the test suite using pytest:

```bash
python -m pytest
```

This will execute all tests in the `tests/` directory and provide coverage information based on the `pytest.ini` or `pyproject.toml` configuration.

---

##  Project Roadmap

-   [x] **Alpha Release**: Initial working version with core CRUD functions.
-   [x] **Testing**: Achieve 100% test coverage via Pytest.
-   [x] **CI/CD**: Implement GitHub Actions for automated testing, build, and release.
-   [x] **Beta Release**: Refine features based on initial testing and usage.
-   [x] **v0.2.0 Release**: Public API, exceptions, transactions, audit trails, soft deletes.
-   [ ] **Community Feedback**: Solicit feedback from users.
-   [ ] **360 Development Review**: Comprehensive internal review of code, docs, and tests.
-   [ ] **Official 1.0 Release**: Stable release suitable for production use.

---

##  Contributing

Contributions are welcome! Please feel free to submit issues, feature requests, or pull requests.

- **💬 [Join the Discussions](https://github.com/fsecada01/SQLModel-CRUD-Utilities/discussions)**: Share your insights, provide feedback, or ask questions.
- **🐛 [Report Issues](https://github.com/fsecada01/SQLModel-CRUD-Utilities/issues)**: Submit bugs found or log feature requests for the `sqlmodel_crud_utils` project.
- **💡 [Submit Pull Requests](https://github.com/fsecada01/SQLModel-CRUD-Utilities/blob/main/CONTRIBUTING.md)**: Review open PRs, and submit your own PRs.
<details closed>
<summary>Contributing Guidelines</summary>

1.  **Fork the Repository**: Start by forking the project repository to your GitHub account.
2.  **Clone Locally**: Clone the forked repository to your local machine.
    ```bash
    git clone https://github.com/fsecada01/SQLModel-CRUD-Utilities.git
    ```
3.  **Create a New Branch**: Always work on a new branch for your changes.
    ```bash
       git checkout -b feature/your-new-feature
    ```
4.  **Make Your Changes**: Implement your feature or bug fix. Add tests!
5.  **Test Your Changes**: Run `pytest` to ensure all tests pass.
6.  **Format and Lint**: Ensure code follows project standards (e.g., using `black`, `ruff`, `pre-commit`).
7.  **Commit Your Changes**: Commit with a clear and concise message.
    ```bash
    git commit -m "feat: Implement the new feature."
    ```
8.  **Push to GitHub**: Push the changes to your forked repository.
    ```bash
    git push origin feature/your-new-feature
    ```
9.  **Submit a Pull Request**: Create a PR against the main branch of the original repository. Clearly describe your changes.
10. **Review**: Wait for code review and address any feedback.

</details>

<details closed>
<summary>Contributor Graph</summary>
<br>
<p align="left">
   <a href="https://github.com/fsecada01/sqlmodel-crud-utils/graphs/contributors">
      <img src="https://contrib.rocks/image?repo=fsecada01/sqlmodel-crud-utils">
   </a>
</p>
</details>

---

##  License

This project is protected under the **MIT License**. For more details, refer to
the [LICENSE file](LICENSE).

---

##  Acknowledgments

- Inspiration drawn from the need to streamline CRUD operations across multiple projects utilizing SQLModel.
-   Built upon the excellent foundations provided by SQLModel and SQLAlchemy.
-   Utilizes Loguru for optional logging and Factory Boy for test data generation.
-   Special thanks to all contributors and users who provide feedback and improvements.

---
