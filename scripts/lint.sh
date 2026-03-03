#!/bin/bash

set -e

echo "Checking code formatting..."
uv run ruff format . --check

echo "Running Ruff linting..."
uv run ruff check .

echo "Running type checking..."
uv run mypy src/

echo "All linting checks passed"
