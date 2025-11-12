FROM python:3.13-slim

WORKDIR /app

# Update system packages and install necessary dependencies
RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
    curl \
    git \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install -e . && \
    pip install requests PyGithub

# Set environment variables
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

# Expose port for FastAPI
EXPOSE 8000

# Create a non-root user for security
# Use build args to allow flexible UID/GID for both dev and prod
ARG USER_ID=1000
ARG GROUP_ID=1000
ARG USERNAME=appuser

# Create group if it doesn't exist, create user, and set ownership
RUN (groupadd -g ${GROUP_ID} ${USERNAME} 2>/dev/null || true) && \
    useradd -u ${USER_ID} -g ${GROUP_ID} -m -s /bin/bash ${USERNAME} && \
    chown -R ${USER_ID}:${GROUP_ID} /app

USER ${USER_ID}:${GROUP_ID}

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/github-report || exit 1

# Start the FastAPI application
CMD ["python", "-m", "uvicorn", "src.agent_mcp_demo.server:app", "--host", "0.0.0.0", "--port", "8000"]
