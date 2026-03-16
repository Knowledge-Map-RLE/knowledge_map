# Dockerfile for NLP Microservice
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install poetry==1.7.1

# Copy dependency files
COPY pyproject.toml poetry.lock* ./

# Configure Poetry to not create virtual environment
RUN poetry config virtualenvs.create false

# Install dependencies
RUN poetry install --no-interaction --no-ansi --no-root

# Copy proto files
COPY proto/ ./proto/

# Generate proto files
RUN python -m grpc_tools.protoc \
    -I./proto \
    --python_out=./src \
    --grpc_python_out=./src \
    ./proto/nlp.proto

# Copy source code
COPY src/ ./src/

# Create model cache directory
RUN mkdir -p /app/models

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

# Expose gRPC port
EXPOSE 50055

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD python -c "import grpc; channel = grpc.insecure_channel('localhost:50055'); channel.close()" || exit 1

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV NLP_HOST=0.0.0.0
ENV NLP_PORT=50055
ENV MODEL_CACHE_DIR=/app/models

# Run gRPC server
CMD ["python", "src/main.py"]
