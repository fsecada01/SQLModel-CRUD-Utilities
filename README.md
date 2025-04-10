<div align="left" style="position: relative;">
<img src="https://raw.githubusercontent.com/PKief/vscode-material-icon-theme/ec559a9f6bfd399b82bb44393651661b08aaf7ba/icons/folder-markdown-open.svg" align="right" width="30%" style="margin: -20px 0 0 20px;">
<h1>SQLMODEL_CRUD_UTILS</h1>
<p align="left">
	<em>A set of CRUD (Create, Read, Update, Delete) utilities designed to
streamline and expedite common database  operations when using SQLModel, offering both synchronous and asynchronous support.</em>
</p>
<p align="left">
	<!-- Add relevant badges here if/when hosted publicly, e.g., PyPI version, build status, coverage -->
    <!-- Example:
    <a href="https://pypi.org/project/sqlmodel-crud-utils/"><img alt="PyPI - Version" src="https://img.shields.io/pypi/v/sqlmodel-crud-utils"></a>
    <a href="https://github.com/YOUR_USERNAME/sqlmodel-crud-utils/actions/workflows/release.yml"><img alt="CI Status" src="https://github.com/YOUR_USERNAME/sqlmodel-crud-utils/actions/workflows/release.yml/badge.svg"></a>
    <a href="https://codecov.io/gh/YOUR_USERNAME/sqlmodel-crud-utils"><img src="https://codecov.io/gh/YOUR_USERNAME/sqlmodel-crud-utils/branch/main/graph/badge.svg"/></a>
     -->
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

- [ Overview](#-overview)
- [Features](#-features)
- [ Project Structure](#-project-structure)
  - [ Project Index](#-project-index)
- [ Getting Started](#-getting-started)
  - [ Prerequisites](#-prerequisites)
  - [ Configuration](#-configuration)
  - [ Installation](#-installation)
  - [ Usage](#-usage)
  - [ Testing](#-testing)
- [ Project Roadmap](#-project-roadmap)
- [ Contributing](#-contributing)
- [ License](#-license)
- [ Acknowledgments](#-acknowledgments)

---

##  Overview
`sqlmodel-crud-utils` provides a convenient layer on top of SQLModel and SQLAlchemy to simplify common database interactions. It offers both synchronous and asynchronous functions for creating, reading, updating, and deleting data, along with helpers for bulk operations, filtering, pagination, and relationship loading. The goal is to reduce boilerplate code in
 projects using SQLModel.

---

##  Features

-   **Sync & Async Support:** Provides parallel functions in `sqlmodel_crud_utils.sync` and `sqlmodel_crud_utils.a_sync`.
-   **Simplified CRUD:** Offers high-level functions:
    - `get_one_or_create`:
    Retrieves an existing record or creates a new one.
    -   `get_row`: Fetches a single row by primary key.
    -   `get_rows`: Fetches multiple rows with flexible filtering, sorting, and pagination.
    -   `get_rows_within_id_list`: Fetches rows matching a list of primary keys.
    -   `update_row`: Updates fields of an existing row.
    -   `delete_row`: Deletes a row by primary key.
    -   `write_row`: Inserts a single new row.
    -   `insert_data_rows`: Inserts multiple new rows with fallback for individual insertion on bulk failure.
    -   `bulk_upsert_mappings`: Performs bulk insert-or-update operations (dialect-aware).
-   **Relationship Loading:** Supports eager loading (`selectinload`) and lazy loading (`lazyload`) via parameters in `get_row` and `get_rows`.
-   **Flexible Filtering:** `get_rows` supports filtering by exact matches (`filter_by`) and common comparisons (`__like`, `__gte`, `__lte`, `__gt`, `__lt`, `__in`) using keyword arguments.
-   **Pagination:** Built-in pagination for `get_rows`.
-   **Dialect-Specific Upsert:** Automatically uses the correct `upsert` syntax (e.g., `ON CONFLICT DO UPDATE` for PostgreSQL/SQLite) based on the `SQL_DIALECT` environment variable.
-   **Error Handling:** Includes basic error logging via `loguru` and session rollback on exceptions.

---

##  Project Structure


```sh
└── sqlmodel_crud_utils/
    ├── __init__.py
    ├── __pycache__
    │   ├── __init__.cpython-313.pyc
    │   ├── a_sync.cpython-313.pyc
    │   ├── sync.cpython-313.pyc
    │   └── utils.cpython-313.pyc
    ├── a_sync.py
    ├── sync.py
    └── utils.py
```


###  Project Index
<details open>
	<summary><b><code>sqlmodel_crud_utils/</code></b></summary>
	<details> <!-- __root__ Submodule -->
		<summary><b>__root__</b></summary>
		<blockquote>
			<table>
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
			</table>
		</blockquote>
	</details>
</details>

---


---
##  Getting Started

###  Prerequisites

-   **Python:** Version 3.8+ recommended.
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

Refer to SQLAlchemy Dialects for a list of supported dialect names.

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

Import the desired functions from either the `sync` or `a_sync` module and use them with your SQLModel session and models.

**Example (Synchronous):**

```python

from sqlmodel import Session, SQLModel, create_engine, Field
from sqlmodel_crud_utils.sync import get_one_or_create, get_rows

# Assume MyModel is defined and engine is created

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
        session_inst=session, model=MyModel,
        name="Test Item", create_method_kwargs={"value": 123}
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
*(See `sync.py` and `a_sync.py` docstrings or the full README examples from previous interactions for more detailed usage)*

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

- inspiration drawn from the need to streamline CRUD operations across multiple projects utilizing SQLModel.
-   Built upon the excellent foundations provided by SQLModel and SQLAlchemy.
-   Utilizes Loguru for logging and Factory Boy for test data generation.

---