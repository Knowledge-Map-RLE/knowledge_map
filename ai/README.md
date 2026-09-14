# AI Agent Microservice

OpenAI-compatible chat gateway for the Knowledge Map. The service does **not**
run models itself — it forwards `/v1/chat/completions` to a configured
OpenAI-compatible provider and streams the reply back unchanged.

- Production: **cloud.ru Foundation Models** (`deepseek-ai/DeepSeek-V4-Flash`)
- During development: local GGUF model via llama-cpp-python + LM Studio fallback.

## Architecture

```
ai/
├── src/
│   ├── config.py           # Settings + provider loading (AI_PROVIDERS / cloud.ru / LM Studio defaults)
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
└── start.ps1               # Local start (port 50059, stale-process cleanup)
```

## Running

```powershell
cd ai
poetry install
.\start.ps1
```

Service listens on **port 50059**. OpenAPI docs: `http://localhost:50059/docs`.

### Quick check

```powershell
curl http://localhost:50059/health
curl http://localhost:50059/v1/models
```

```powershell
curl -X POST http://localhost:50059/v1/chat/completions `
  -H "Content-Type: application/json" `
  -d '{"model":"deepseek-ai/DeepSeek-V4-Flash","messages":[{"role":"user","content":"Hello"}],"stream":false}'
```

## Configuration (`.env`)

| Variable | Description | Default |
|---|---|---|
| `AI_HOST` / `AI_PORT` | Bind address of the gateway | `0.0.0.0` / `50059` |
| `DEFAULT_PROVIDER` | Provider used when no model is given | `cloudru` |
| `DEFAULT_MODEL` | Default model | `deepseek-ai/DeepSeek-V4-Flash` |
| `CLOUDRU_API_KEY` | cloud.ru Foundation Models API key | — |
| `CLOUDRU_MODEL` | Model id (cloud.ru) | `deepseek-ai/DeepSeek-V4-Flash` |
| `AI_BASE_URL` | LM Studio base URL (provider shorthand) | `http://localhost:1234/v1` |
| `AI_API_KEY` | Key sent to the provider (LM Studio ignores it) | `lm-studio` |
| `SYSTEM_PROMPT` | Persona prepended when the client sends no system message | — |
| `AI_PROVIDERS` | Optional JSON list of providers (overrides defaults) | — |
| `AI_REQUEST_TIMEOUT` / `AI_CONNECT_TIMEOUT` | HTTP timeouts | `1800` / `15` |
| `AI_MODELS_CACHE_TTL` | `GET /v1/models` probe cache TTL | `60` |
| `LOG_LEVEL` | Logging level | `INFO` |

## cloud.ru Foundation Models

The `cloudru` provider uses the OpenAI-compatible endpoint at `https://foundation-models.api.cloud.ru/v1` with the model `deepseek-ai/DeepSeek-V4-Flash`. Set `CLOUDRU_API_KEY` in your environment to enable it.

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
