# See here for image contents: https://github.com/microsoft/vscode-dev-containers/tree/v0.245.0/containers/python-3
ARG VARIANT=3.11-bullseye
FROM mcr.microsoft.com/devcontainers/python:${VARIANT}

# Install uv - fast Python package installer
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    mkdir -p /usr/local/bin && \
    if [ -f /root/.cargo/bin/uv ]; then \
        mv /root/.cargo/bin/uv /usr/local/bin/uv; \
    elif [ -f /root/.local/bin/uv ]; then \
        mv /root/.local/bin/uv /usr/local/bin/uv; \
    fi && \
    chmod +x /usr/local/bin/uv && \
    uv --version
