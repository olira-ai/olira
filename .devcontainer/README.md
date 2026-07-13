# Development container

VS Code dev container for the Olira Python SDK.

## Setup

1. Open this repository in VS Code.
2. Install the [Dev Containers](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers) extension.
3. **Reopen in Container** (Command Palette → Dev Containers: Reopen in Container).
4. After the container builds: `bash scripts/install-dev.sh` (PyPI only)

API reference: [https://docs.olira.ai/reference/sdk](https://docs.olira.ai/reference/sdk).

## Commands

- Pre-PR: `./scripts/pre-pr.sh`
- Lint: `./scripts/lint.sh`
- Tests: `./scripts/test.sh`
- Version check: `./scripts/check-version.sh`
