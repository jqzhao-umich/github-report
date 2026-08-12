# -----------------------------------------------------------------------------
# Build stage — resolves and installs the project from uv.lock so the image
# matches the lockfile exactly (PROJECT_REVIEW.md medium finding: enforce lock).
# -----------------------------------------------------------------------------
FROM python:3.13-slim AS build

WORKDIR /app

# Only what's needed to build wheels. curl fetches uv; git is only
# required if a dependency source is a git ref.
RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y --no-install-recommends curl ca-certificates && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Install a pinned uv release. Must be new enough to parse the
# lockfile format we ship — uv.lock declares `revision = 3`, which
# needs uv >= 0.6 (revision 3 landed in 0.6.0). We pin to 0.11.14
# because it matches what the reviewer used to validate the lock;
# bump this in lockstep with any future `uv lock` regeneration.
# Using the standalone installer keeps the build-stage image small
# and avoids pulling astral-sh's own container.
ENV UV_VERSION=0.11.14
RUN curl -LsSf https://astral.sh/uv/${UV_VERSION}/install.sh | sh && \
    mv /root/.local/bin/uv /usr/local/bin/uv

# Copy lock-related manifests before source so a source-only change
# doesn't invalidate the dependency install cache.
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/

# Install the project + its locked deps into a virtualenv we can copy
# straight into the runtime stage. --frozen refuses to touch the lock,
# --no-dev drops test/build-only groups, and the resolved set is
# byte-for-byte what uv.lock records.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
RUN uv sync --frozen --no-dev --no-cache

# -----------------------------------------------------------------------------
# Runtime stage — slim image with just the built venv, no build tools,
# no test runner, no uv, and non-root by default.
# -----------------------------------------------------------------------------
FROM python:3.13-slim AS runtime

WORKDIR /app

# git stays in the runtime because ReportPublisher/GitOperations shells
# out to it for the auto-commit path. curl is kept only for the health
# check; consider dropping it if you replace the HEALTHCHECK with a
# python-native probe.
RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y --no-install-recommends git curl ca-certificates && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Bring in the pre-built environment and the application source.
COPY --from=build /opt/venv /opt/venv
COPY --from=build /app/src /app/src
COPY --from=build /app/pyproject.toml /app/pyproject.toml
COPY --from=build /app/README.md /app/README.md

ENV PATH="/opt/venv/bin:${PATH}"
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Non-root user with configurable UID/GID for dev parity.
ARG USER_ID=1000
ARG GROUP_ID=1000
ARG USERNAME=appuser
RUN (groupadd -g ${GROUP_ID} ${USERNAME} 2>/dev/null || true) && \
    useradd -u ${USER_ID} -g ${GROUP_ID} -m -s /bin/bash ${USERNAME} && \
    chown -R ${USER_ID}:${GROUP_ID} /app
USER ${USER_ID}:${GROUP_ID}

HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/github-report || exit 1

CMD ["python", "-m", "uvicorn", "src.agent_mcp_demo.server:app", "--host", "0.0.0.0", "--port", "8000"]
