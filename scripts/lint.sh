#!/bin/bash

set -e

bash scripts/install-dev.sh

echo "Checking code formatting..."
bash scripts/uv.sh run ruff format . --check

echo "Running Ruff linting..."
bash scripts/uv.sh run ruff check .

echo "Running type checking..."
bash scripts/uv.sh run mypy src/

echo "All linting checks passed"
