# AI Agent Microservice

OpenAI-compatible chat gateway for the Knowledge Map. The service does **not**
run models itself — it forwards `/v1/chat/completions` to a configured
OpenAI-compatible provider and streams the reply back unchanged.

- Providers and model profiles are stored in the shared `config/models.toml` registry.
- LM Studio, cloud.ru and the legacy local GGUF provider can coexist; the active
  profile is selected explicitly and never falls back to the first provider.

## Architecture

```
ai/
├── src/
│   ├── config.py           # Settings + shared model-registry provider loading
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
  -d '{"model":"openai_gpt6_luna","messages":[{"role":"user","content":"Привет"}],"stream":false}'
```

## Configuration (`.env`)

| Variable | Description | Default |
|---|---|---|
| `AI_HOST` / `AI_PORT` | Bind address of the gateway | `0.0.0.0` / `50059` |
| `MODEL_CONFIG_PATH` | Shared TOML registry path | `../config/models.toml` |
| `MODEL_PROFILE` | Active profile override | registry `active_profile` |
| `OPENAI_API_KEY` | OpenAI API key for the Responses provider | — |
| `CLOUDRU_API_KEY` | Optional cloud.ru provider key | — |
| `AI_BASE_URL` | Legacy LM Studio setting; registry is authoritative | `http://localhost:1234/v1` |
| `AI_API_KEY` | Key sent to the provider (LM Studio ignores it) | `lm-studio` |
| `SYSTEM_PROMPT` | Persona prepended when the client sends no system message | — |
| `AI_REQUEST_TIMEOUT` / `AI_CONNECT_TIMEOUT` | HTTP timeouts | `1800` / `15` |
| `AI_MODELS_CACHE_TTL` | `GET /v1/models` probe cache TTL | `60` |
| `LOG_LEVEL` | Logging level | `INFO` |

## OpenAI GPT-6 Luna

The default profile is `openai_gpt6_luna` and uses the Responses API with
`reasoning_effort=max`, a 1,050,000-token context window, and up to 128,000
output tokens. For local development, put `OPENAI_API_KEY` in
`ai/.env.development`; Docker Compose reads it from the repository-root `.env`.
The gateway loads this key into its configured provider without logging it.

To run the existing local Qwen3 profile instead, use:

```powershell
.\scripts\model-profile.ps1 list
.\scripts\model-profile.ps1 use local_qwen3_8b
```

The Qwen3 8B profile and its `40960`-token context remain available. Restart the
AI gateway on port 50059 and API on port 8000 after changing the selected profile.

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
