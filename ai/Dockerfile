# Multi-stage Dockerfile with CUDA support for AI Model Service
# Stage 1: Base image with CUDA (for GPU support)
FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04 AS cuda-base

# Install Python 3.12
RUN apt-get update && apt-get install -y \
    software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y \
    python3.12 \
    python3.12-dev \
    python3.12-distutils \
    python3-pip \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set python3.12 as default python
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1 \
    && update-alternatives --install /usr/bin/python python /usr/bin/python3.12 1

# Upgrade pip
RUN python3 -m pip install --upgrade pip

# Stage 2: CPU-only base (fallback)
FROM python:3.12-slim AS cpu-base

RUN apt-get update && apt-get install -y \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Stage 3: Final image (defaults to CUDA, can be overridden)
ARG USE_CUDA=true
FROM ${USE_CUDA:+cuda-base}${USE_CUDA:-cpu-base} AS final

WORKDIR /app

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
    ./proto/ai_model.proto

# Copy source code
COPY src/ ./src/

# Create model cache directory
RUN mkdir -p /app/models

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

# Expose gRPC port
EXPOSE 50054

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import grpc; channel = grpc.insecure_channel('localhost:50054'); channel.close()" || exit 1

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV GRPC_HOST=0.0.0.0
ENV GRPC_PORT=50054

# Run gRPC server
CMD ["python", "src/grpc_server.py"]
