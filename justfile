# SQLModel CRUD Utils - Task Runner

set shell := ["cmd.exe", "/c"]

# Default recipe - show available commands
default:
    @just --list

# ═══════════════════════════════════════════════════════════════════════════════
# Claude Code
# ═══════════════════════════════════════════════════════════════════════════════

# Start Claude Code (autonomous mode)
claude *ARGS="":
    claude --allow-dangerously-skip-permissions {{ ARGS }}

# Continue last Claude session
claude-continue:
    claude --continue

# Resume a specific Claude session
claude-resume:
    claude --resume

# Start Claude with a one-shot prompt
claude-prompt PROMPT:
    claude -p "{{ PROMPT }}"

# ═══════════════════════════════════════════════════════════════════════════════
# Dependencies
# ═══════════════════════════════════════════════════════════════════════════════

# Sync Python dependencies with uv
sync *args='':
    uv sync {{args}}

# Lock Python dependencies with uv
lock:
    uv lock

# Install development dependencies
install:
    uv sync --all-extras

# ═══════════════════════════════════════════════════════════════════════════════
# Code Quality
# ═══════════════════════════════════════════════════════════════════════════════

# Run all linters and formatters (ruff, isort, black, type check)
lint:
    ruff check --fix .
    isort .
    black .
    ty check .

# Run all pre-commit hooks
check:
    pre-commit run --all-files

# Type check only
type-check:
    ty check .

# Ruff check only
ruff:
    ruff check .

# Ruff check with auto-fix
ruff-fix:
    ruff check --fix .

# Black format only
black:
    black .

# isort only
isort:
    isort .

# ═══════════════════════════════════════════════════════════════════════════════
# Testing
# ═══════════════════════════════════════════════════════════════════════════════

# Run all tests with coverage
test:
    python -m pytest

# Run tests with verbose output
test-v:
    python -m pytest -v

# Run tests and show coverage report
test-cov:
    python -m pytest --cov=sqlmodel_crud_utils --cov-report=html --cov-report=term

# Run specific test file
test-file FILE:
    python -m pytest {{FILE}}

# Run tests matching a pattern
test-k PATTERN:
    python -m pytest -k {{PATTERN}}

# ═══════════════════════════════════════════════════════════════════════════════
# Documentation
# ═══════════════════════════════════════════════════════════════════════════════

# Generate documentation with pdoc
docs:
    uv run --with pdoc pdoc sqlmodel_crud_utils -o docs

# Serve documentation locally
docs-serve:
    uv run --with pdoc pdoc sqlmodel_crud_utils

# ═══════════════════════════════════════════════════════════════════════════════
# Build & Release
# ═══════════════════════════════════════════════════════════════════════════════

# Clean build artifacts
clean:
    if exist dist rmdir /s /q dist
    if exist build rmdir /s /q build
    if exist *.egg-info rmdir /s /q *.egg-info
    if exist htmlcov rmdir /s /q htmlcov
    if exist .pytest_cache rmdir /s /q .pytest_cache
    if exist .coverage del /q .coverage

# Build distribution packages
build: clean
    python -m build

# Build and check package
build-check: build
    twine check dist/*

# Upload to PyPI (production)
publish: build-check
    twine upload dist/*

# Upload to TestPyPI (testing)
publish-test: build-check
    twine upload --repository testpypi dist/*

# ═══════════════════════════════════════════════════════════════════════════════
# Git Workflow
# ═══════════════════════════════════════════════════════════════════════════════

# Show git status
status:
    rtk git status

# Show git log
log:
    rtk git log --oneline -10

# Create and push a new tag (e.g., just tag 0.2.0)
tag VERSION:
    rtk git tag -a v{{VERSION}} -m "Release v{{VERSION}}"
    rtk git push origin v{{VERSION}}

# ═══════════════════════════════════════════════════════════════════════════════
# Development Workflows
# ═══════════════════════════════════════════════════════════════════════════════

# Full pre-commit workflow (lint, type check, test)
pre-commit: lint test

# Prepare for release (lint, test, build, check)
release-prep: lint test build-check
    @echo "Ready for release! Run 'just publish' to upload to PyPI"

# Quick development cycle (format and test)
dev: ruff-fix black isort test
