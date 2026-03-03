#!/usr/bin/env bash

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}Running pre-PR validation for olira-sdk-python...${NC}"
echo "========================================================="

echo ""
echo -e "${BLUE}Step 1: Version consistency...${NC}"
bash scripts/check-version.sh

echo ""
echo -e "${BLUE}Step 2: Formatting and linting...${NC}"
uv run ruff format .
uv run ruff check . --fix --quiet
uv run ruff format . --check
uv run ruff check .
uv run mypy src/

echo ""
echo -e "${BLUE}Step 3: Tests...${NC}"
uv run pytest tests/ --tb=short --durations=10

echo ""
echo -e "${GREEN}All pre-PR checks passed.${NC}"
