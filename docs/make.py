#!/usr/bin/env python3
"""
Documentation build script for sqlmodel-crud-utils.

This script generates the API reference documentation using pdoc
while preserving the custom landing page, use-cases, and recipes pages.
"""

import shutil
import subprocess
import sys
from pathlib import Path

# Get the project root (parent of docs/)
DOCS_DIR = Path(__file__).parent
PROJECT_ROOT = DOCS_DIR.parent

# Files to preserve (our custom documentation pages)
PRESERVE_FILES = [
    "index.html",
    "use-cases.html",
    "recipes.html",
]


def main() -> int:
    """Build the documentation."""
    print("Building sqlmodel-crud-utils documentation...")

    # Backup custom files
    print("\n1. Backing up custom documentation pages...")
    backup_dir = DOCS_DIR / ".backup"
    backup_dir.mkdir(exist_ok=True)

    for filename in PRESERVE_FILES:
        file_path = DOCS_DIR / filename
        if file_path.exists():
            backup_path = backup_dir / filename
            shutil.copy2(file_path, backup_path)
            print(f"   [OK] Backed up {filename}")

    # Generate API documentation with pdoc
    print("\n2. Generating API reference with pdoc...")
    try:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pdoc",
                "sqlmodel_crud_utils",
                "-o",
                str(DOCS_DIR),
            ],
            check=True,
            cwd=PROJECT_ROOT,
        )
        print("   [OK] API documentation generated")
    except subprocess.CalledProcessError as e:
        print(f"   [ERROR] Failed to generate API documentation: {e}")
        return 1

    # Restore custom files
    print("\n3. Restoring custom documentation pages...")
    for filename in PRESERVE_FILES:
        backup_path = backup_dir / filename
        if backup_path.exists():
            file_path = DOCS_DIR / filename
            shutil.copy2(backup_path, file_path)
            print(f"   [OK] Restored {filename}")

    # Cleanup backup directory
    shutil.rmtree(backup_dir)
    print("\n[OK] Documentation build complete!")

    return 0


if __name__ == "__main__":
    sys.exit(main())
