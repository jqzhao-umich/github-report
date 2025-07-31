FROM python:3.13-slim

WORKDIR /app

# Update system packages and install necessary dependencies
RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
    curl \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install -e .

# Set environment variables
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

# Expose port for FastAPI
EXPOSE 8000

# Create a non-root user for security
RUN useradd --create-home --shell /bin/bash app && \
    chown -R app:app /app
USER app

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/github-report || exit 1

# Start the FastAPI application
CMD ["python", "-m", "uvicorn", "src.agent_mcp_demo.server:app", "--host", "0.0.0.0", "--port", "8000"]
