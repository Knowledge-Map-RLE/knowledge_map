# AI Agent Microservice

OpenAI-compatible chat gateway for the Knowledge Map. The service does **not**
run models itself — it forwards `/v1/chat/completions` to a configured
OpenAI-compatible provider and streams the reply back unchanged.

- During development: **LM Studio** (`http://localhost:1234/v1`, model `qwen/qwen3-4b`).
- Later: **DeepSeek Pro / Flash** (and any other OpenAI-compatible endpoint).

## Architecture

```
ai/
├── src/
│   ├── config.py           # Settings + provider loading (AI_PROVIDERS / LM Studio defaults)
│   ├── providers.py        # Provider registry, model->provider resolution, httpx client
│   ├── schemas.py          # OpenAI-compatible chat request schema
│   ├── app.py              # FastAPI app factory (CORS, routers)
│   ├── main.py             # uvicorn entry point
│   └── routers/
│       ├── health.py       # GET /health
│       ├── models.py       # GET /v1/models
│       └── chat.py         # POST /v1/chat/completions (stream + plain)
├── tests/unit/test_chat.py # Endpoint tests with a fake provider
├── Dockerfile              # Python 3.12, stateless
├── pyproject.toml
└── start.ps1               # Local start (port 50054, stale-process cleanup)
```

## Running

```powershell
cd ai
poetry install
.\start.ps1
```

Service listens on **port 50054**. OpenAPI docs: `http://localhost:50054/docs`.

### Quick check

```powershell
curl http://localhost:50054/health
curl http://localhost:50054/v1/models
```

```powershell
curl -X POST http://localhost:50054/v1/chat/completions `
  -H "Content-Type: application/json" `
  -d '{"model":"qwen/qwen3-4b","messages":[{"role":"user","content":"Hello"}],"stream":false}'
```

## Configuration (`.env`)

| Variable | Description | Default |
|---|---|---|
| `AI_HOST` / `AI_PORT` | Bind address of the gateway | `0.0.0.0` / `50054` |
| `DEFAULT_PROVIDER` | Provider used when no model is given | `lm-studio` |
| `DEFAULT_MODEL` | Default model | `qwen/qwen3-4b` |
| `AI_BASE_URL` | LM Studio base URL (provider shorthand) | `http://localhost:1234/v1` |
| `AI_API_KEY` | Key sent to the provider (LM Studio ignores it) | `lm-studio` |
| `SYSTEM_PROMPT` | Persona prepended when the client sends no system message | — |
| `AI_PROVIDERS` | Optional JSON list of providers (overrides defaults) | — |
| `AI_REQUEST_TIMEOUT` / `AI_CONNECT_TIMEOUT` | HTTP timeouts | `300` / `15` |
| `AI_MODELS_CACHE_TTL` | `GET /v1/models` probe cache TTL | `60` |
| `LOG_LEVEL` | Logging level | `INFO` |

### Adding DeepSeek Pro / Flash

Set `AI_PROVIDERS` in `.env`:

```json
[
  {"name": "lm-studio",   "base_url": "http://localhost:1234/v1", "api_key": "lm-studio", "models": ["qwen/qwen3-4b"]},
  {"name": "deepseek-pro", "base_url": "https://api.deepseek.com/v1", "api_key": "sk-...", "models": ["deepseek-chat"]},
  {"name": "deepseek-flash", "base_url": "https://api.deepseek.com/v1", "api_key": "sk-...", "models": ["deepseek-flash"]}
]
```

Model lookup order: exact match in a provider's `models`, `default`, or `<provider>/<model>` prefix.

## Testing

```powershell
poetry run pytest
```

## API surface (OpenAI-compatible)

- `GET /health` — service status.
- `GET /v1/models` — configured + live-loaded models (cached `AI_MODELS_CACHE_TTL` s).
- `POST /v1/chat/completions` — OpenAI `chat/completions` body. Supports
  `"stream": true` (SSE passthrough). A `system` message is injected from
  `SYSTEM_PROMPT` if the client did not send one.

Errors are returned as `{"error": {"message": "...", "type": "invalid_request_error"}}`.
