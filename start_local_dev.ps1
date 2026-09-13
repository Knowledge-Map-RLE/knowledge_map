$root = $PSScriptRoot

# Development-окружение для всех сервисов (процессная переменная наследуется
# вкладками Windows Terminal -> start.ps1 сервисов выбирает .env.development).
$env:ENVIRONMENT = 'development'

# Локальные (не-Docker) сервисы дублируют logfmt-логи в файлы,
# Alloy тайлит эту директорию → Loki.
$env:WRITE_LOGS_TO = "$root\data\dev_logs"

# Общие OTLP-параметры для локальных Python-процессов (OTEL_SERVICE_NAME
# задаётся в каждом start.ps1 индивидуально).
$env:OTEL_EXPORTER_OTLP_ENDPOINT = "http://127.0.0.1:4317"
$env:OTEL_SERVICE_VERSION = "0.1.0"
$env:OTEL_METRIC_EXPORT_INTERVAL = "30000"
$env:LOG_FORMAT = "logfmt"

wt new-tab -d "$root\api" --title "API" powershell.exe -NoExit -Command ".\start.ps1" `; new-tab -d "$root" --title "Neo4j" powershell.exe -NoExit -Command "docker compose up neo4j" `; new-tab -d "$root" --title "S3" powershell.exe -NoExit -Command "docker compose up s3" `; new-tab -d "$root" --title "Qdrant" powershell.exe -NoExit -Command "docker compose up qdrant" `; new-tab -d "$root" --title "Observability" powershell.exe -NoExit -Command "docker compose up loki tempo prometheus alloy grafana" `; new-tab -d "$root\auth" --title "Auth" powershell.exe -NoExit -Command ".\start.ps1" `; new-tab -d "$root\billing" --title "Billing" powershell.exe -NoExit -Command ".\start.ps1" `; new-tab -d "$root\client" --title "Client" powershell.exe -NoExit -Command "bun dev" `; new-tab -d "$root\nlp" --title "NLP" powershell.exe -NoExit -Command ".\start.ps1" `; new-tab -d "$root\pdf_to_md" --title "pdf_to_md" powershell.exe -NoExit -Command ".\start.ps1" `; new-tab -d "$root\xml_to_md" --title "xml_to_md" powershell.exe -NoExit -Command ".\start.ps1" `; new-tab -d "$root\data_to_db" --title "data_to_db" powershell.exe -NoExit -Command ".\start.ps1" `; new-tab -d "$root\ai" --title "AI" powershell.exe -NoExit -Command ".\start.ps1" `; new-tab -d "$root\laying" --title "Layout" powershell.exe -NoExit -Command ".\start.ps1" `; new-tab -d "$root\knowledge_map_core" --title "KnowledgeLang" powershell.exe -NoExit -Command ".\start.ps1"
