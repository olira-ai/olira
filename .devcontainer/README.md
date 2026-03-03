# Development Container

VS Code dev container for the Olira Python SDK. Matches the pattern used by `packages/common-models` for a consistent monorepo experience.

## Features

- **Python 3.11** with uv for dependency management
- **VS Code extensions**: Python, Pylance, Ruff, MyPy, GitLens
- **Linting & formatting**: Ruff and MyPy with project config
- **AWS CLI**: For CodeArtifact when publishing
- **Named volumes** for venv and caches (faster on macOS)

## Usage

1. Open `packages/olira-sdk-python` in VS Code.
2. Install the [Dev Containers](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers) extension.
3. **Reopen in Container** (Command Palette → “Dev Containers: Reopen in Container”).
4. After the container builds, `postCreateCommand` runs `uv sync --all-extras` (uses PyPI; CodeArtifact optional for publishing).

## Commands

- Pre-PR: `./scripts/pre-pr.sh`
- Lint: `./scripts/lint.sh`
- Tests: `./scripts/test.sh`
- Version check: `./scripts/check-version.sh`

## Manual install (no CodeArtifact)

Dependencies are on PyPI, so the container will run `uv sync` without a token. If sync fails due to index config, run:

```bash
UV_INDEX_URL=https://pypi.org/simple/ uv sync --all-extras
```
