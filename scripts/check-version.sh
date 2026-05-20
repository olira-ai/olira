#!/usr/bin/env bash

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}Checking version consistency and changelog entry...${NC}"
echo "========================================================="

get_pyproject_version() {
    grep -E '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/' || echo ""
}

get_version_py_version() {
    grep -E '^__version__ = ' src/olira/version.py | sed 's/__version__ = "\(.*\)"/\1/' || echo ""
}

get_changelog_version() {
    if [ -f CHANGELOG.md ]; then
        grep -E '^## \[?[0-9]+\.[0-9]+\.[0-9]+' CHANGELOG.md | head -1 | sed -E 's/^## \[?([0-9]+\.[0-9]+\.[0-9]+(-[^]]+)?)\]?.*/\1/' || echo ""
    else
        echo ""
    fi
}

PYPROJECT_VERSION=$(get_pyproject_version)
VERSION_PY_VERSION=$(get_version_py_version)
CHANGELOG_VERSION=$(get_changelog_version)

echo ""
echo -e "${BLUE}Found versions:${NC}"
echo "  - pyproject.toml: ${PYPROJECT_VERSION:-<not found>}"
echo "  - src/olira/version.py: ${VERSION_PY_VERSION:-<not found>}"
echo "  - CHANGELOG.md: ${CHANGELOG_VERSION:-<not found>}"

if [ -z "$PYPROJECT_VERSION" ]; then
    echo -e "${RED}ERROR: Could not find version in pyproject.toml${NC}"
    exit 1
fi

if [ -z "$VERSION_PY_VERSION" ]; then
    echo -e "${RED}ERROR: Could not find version in src/olira/version.py${NC}"
    exit 1
fi

if [ -z "$CHANGELOG_VERSION" ]; then
    echo -e "${RED}ERROR: Could not find version entry in CHANGELOG.md${NC}"
    echo -e "${RED}   Add a changelog entry with format: '## [version]' or '## version'${NC}"
    exit 1
fi

if [ "$PYPROJECT_VERSION" != "$VERSION_PY_VERSION" ]; then
    echo -e "${RED}ERROR: Version mismatch!${NC}"
    echo -e "${RED}   pyproject.toml: $PYPROJECT_VERSION${NC}"
    echo -e "${RED}   src/olira/version.py: $VERSION_PY_VERSION${NC}"
    exit 1
fi

PYPROJECT_BASE=$(echo "$PYPROJECT_VERSION" | sed 's/-.*//')
CHANGELOG_BASE=$(echo "$CHANGELOG_VERSION" | sed 's/-.*//')

if [ "$PYPROJECT_BASE" != "$CHANGELOG_BASE" ]; then
    echo -e "${YELLOW}WARNING: Changelog version ($CHANGELOG_VERSION) doesn't match project version ($PYPROJECT_VERSION)${NC}"
fi

if [ "${CI:-false}" = "true" ] && [ -n "${GITHUB_BASE_REF:-}" ]; then
    echo ""
    echo -e "${BLUE}Checking if version changed from base branch ($GITHUB_BASE_REF)...${NC}"
    BASE_VERSION=$(git show "origin/${GITHUB_BASE_REF}:packages/olira-sdk-python/pyproject.toml" 2>/dev/null | grep -E '^version = ' | sed 's/version = "\(.*\)"/\1/' || echo "")
    if [ -z "$BASE_VERSION" ]; then
        echo -e "${YELLOW}Could not determine base branch version, skipping change check${NC}"
    elif [ "$PYPROJECT_VERSION" = "$BASE_VERSION" ]; then
        echo -e "${RED}ERROR: Version has not been changed!${NC}"
        echo -e "${RED}   Current: $PYPROJECT_VERSION, Base: $BASE_VERSION${NC}"
        exit 1
    else
        echo -e "${GREEN}Version changed from $BASE_VERSION to $PYPROJECT_VERSION${NC}"
    fi
elif command -v git &> /dev/null && git rev-parse --git-dir &> /dev/null; then
    BASE_BRANCH=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@' || echo "main")
    BASE_VERSION=$(git show "origin/${BASE_BRANCH}:packages/olira-sdk-python/pyproject.toml" 2>/dev/null | grep -E '^version = ' | sed 's/version = "\(.*\)"/\1/' || echo "")

    if [ -n "$BASE_VERSION" ] && [ "$PYPROJECT_VERSION" = "$BASE_VERSION" ]; then
        echo ""
        echo -e "${YELLOW}WARNING: Version matches base branch ($BASE_BRANCH) version: $BASE_VERSION${NC}"
        echo -e "${YELLOW}   Consider updating the version if this is a new release${NC}"
    elif [ -n "$BASE_VERSION" ]; then
        echo ""
        echo -e "${GREEN}Version changed from $BASE_VERSION to $PYPROJECT_VERSION${NC}"
    fi
fi

echo ""
echo -e "${GREEN}Version check passed: $PYPROJECT_VERSION${NC}"
