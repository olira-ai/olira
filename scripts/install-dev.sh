#!/usr/bin/env bash

# Public package install — PyPI only; no CodeArtifact or AWS auth required.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PACKAGE_DIR"

if ! command -v uv &> /dev/null; then
    echo "uv is required but not installed. Install it with:"
    echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

echo "Installing olira-sdk-python dependencies from PyPI..."
bash scripts/uv.sh sync --frozen --extra dev

echo "Setup complete."
