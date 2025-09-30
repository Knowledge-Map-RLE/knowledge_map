# Multi-stage Dockerfile для high-performance Rust микросервиса

# Этап 1: Сборка
FROM rust:1.75-slim as builder

# Установка системных зависимостей для сборки
RUN apt-get update && apt-get install -y \
    pkg-config \
    libssl-dev \
    protobuf-compiler \
    && rm -rf /var/lib/apt/lists/*

# Создание рабочей директории
WORKDIR /app

# Копирование файлов зависимостей для кеширования
COPY Cargo.toml Cargo.lock ./
COPY build.rs ./
COPY proto/ ./proto/

# Создание пустого src для сборки зависимостей
RUN mkdir src && echo "fn main() {}" > src/main.rs

# Сборка зависимостей (будет закешировано)
RUN cargo build --release --bin graph-layout-server
RUN rm src/main.rs

# Копирование исходного кода
COPY src/ ./src/

# Финальная сборка с оптимизациями
RUN cargo build --release --bin graph-layout-server

# Этап 2: Runtime образ
FROM debian:bookworm-slim

# Установка runtime зависимостей
RUN apt-get update && apt-get install -y \
    ca-certificates \
    libssl3 \
    && rm -rf /var/lib/apt/lists/*

# Создание пользователя для безопасности
RUN useradd --create-home --shell /bin/bash app

# Создание рабочей директории
WORKDIR /app

# Копирование бинарного файла из builder stage
COPY --from=builder /app/target/release/graph-layout-server /usr/local/bin/

# Копирование конфигурации
COPY config.toml ./

# Установка владельца
RUN chown -R app:app /app

# Переключение на непривилегированного пользователя
USER app

# Настройки окружения для производительности
ENV RUST_LOG=info
ENV RUST_BACKTRACE=1

# Настройки памяти для high-performance
ENV MALLOC_ARENA_MAX=4
ENV MALLOC_MMAP_THRESHOLD_=131072
ENV MALLOC_TRIM_THRESHOLD_=131072
ENV MALLOC_TOP_PAD_=131072
ENV MALLOC_MMAP_MAX_=65536

# Экспорт портов
EXPOSE 50051 9090

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD /usr/local/bin/graph-layout-server --mode health || exit 1

# Команда запуска
CMD ["/usr/local/bin/graph-layout-server", "--mode", "server"]
