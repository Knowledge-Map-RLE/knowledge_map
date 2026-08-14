# Multi-stage Dockerfile for the Billing microservice.
# Подписки, платежи (ЮKassa) и кредиты.

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

# Generate gRPC stubs for auth.proto
COPY proto/ ./proto/
RUN mkdir -p utils/generated \
    && poetry run python -m grpc_tools.protoc \
        -I./proto \
        --python_out=./utils/generated \
        --grpc_python_out=./utils/generated \
        ./proto/auth.proto \
    && touch utils/generated/__init__.py

# Copy source code
COPY src/ ./src/

# Create a non-root user for security
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

# Expose the HTTP port
EXPOSE 50058

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=5 \
    CMD curl -fsS http://localhost:50058/billing/health || exit 1

ENV PYTHONUNBUFFERED=1
ENV BILLING_HOST=0.0.0.0
ENV BILLING_PORT=50058

# Run the uvicorn entry point
CMD ["python", "src/main.py"]
