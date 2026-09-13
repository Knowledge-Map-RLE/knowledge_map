# knowledge-map-observability

Общий пакет наблюдаемости микросервисов Knowledge Map:

- **Traces** — OpenTelemetry SDK + OTLP (gRPC) экспорт в Grafana Alloy → Tempo
- **Metrics** — OpenTelemetry Metrics SDK + OTLP (gRPC) → Alloy → Prometheus (remote_write)
- **Logs** — единый logfmt-форматтер в stdout → Docker → Loki

Использование:

```python
from observability import (
    init_telemetry,
    setup_logging,
    instrument_fastapi,
    instrument_grpc_server,
    instrument_httpx,
)

setup_logging(service_name="api")   # logfmt в stdout, без файлов
init_telemetry(service_name="api")  # OTLP-экспортеры
instrument_fastapi()
```

Конфигурация — стандартными `OTEL_*` переменными окружения (см. `observability/__init__.py`).