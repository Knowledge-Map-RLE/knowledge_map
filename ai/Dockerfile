# Multi-stage Dockerfile for the AI Agent microservice.
# The service is a stateless OpenAI-compatible chat gateway — no GPU needed.

FROM python:3.12-slim AS final

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install poetry==1.7.1

# Copy dependency files
COPY pyproject.toml poetry.lock* ./

# Configure Poetry to not create a virtual environment
RUN poetry config virtualenvs.create false

# Install dependencies
RUN poetry install --no-interaction --no-ansi --no-root

# Copy source code
COPY src/ ./src/

# Create a non-root user for security
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

# Expose the HTTP port
EXPOSE 50059

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:50059/health || exit 1

ENV PYTHONUNBUFFERED=1
ENV AI_HOST=0.0.0.0
ENV AI_PORT=50059

# Run the uvicorn entry point
CMD ["python", "src/main.py"]
