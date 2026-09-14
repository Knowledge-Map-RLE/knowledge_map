"""Configuration for the AI Agent microservice.

The service is an OpenAI-compatible chat gateway. It knows nothing about specific
models: it forwards ``/v1/chat/completions`` requests to one of the configured
providers (cloud.ru Foundation Models, LM Studio during development, a local GGUF
model via llama-cpp-python) and streams the reply back in OpenAI format.

Environment split
-----------------
The service reads ``.env.<ENVIRONMENT>`` when ``ENVIRONMENT`` is set in the
process environment (or defaults to ``development`` locally), falling back to
``.env``. Example: ``ai/.env.development`` holds the development provider
configuration, ``ai/.env.production`` would hold production secrets.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Provider(BaseModel):
    """An upstream provider (cloud.ru, LM Studio, local GGUF, ...).

    All HTTP-based providers use ``HttpProviderClient`` (OpenAI-compatible).

    ``use_local`` marks a provider implemented by ``LocalGGUFProviderClient``
    (llama-cpp-python + HuggingFace Hub).
    """

    name: str
    base_url: str
    api_key: str | None = None
    models: list[str] = Field(default_factory=list)
    default_model: str | None = None
    context_length: int | None = None
    use_local: bool = False


def _resolve_env_file() -> str:
    """Pick ``<service_dir>/.env.<ENVIRONMENT>`` else ``.env`` (absolute path)."""
    service_dir = Path(__file__).resolve().parents[1]
    env = os.environ.get("ENVIRONMENT", "development")
    candidate = service_dir / f".env.{env}"
    if candidate.is_file():
        return str(candidate)
    base = service_dir / ".env"
    return str(base) if base.is_file() else ""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_resolve_env_file(),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    host: str = Field(default="0.0.0.0", alias="AI_HOST")
    port: int = Field(default=50059, alias="AI_PORT")

    # Deployment environment: development / staging / production.
    environment: str = Field(default="development", alias="ENVIRONMENT")

    # Provider/model used when the client does not specify one.
    default_provider: str = Field(default="lm-studio", alias="DEFAULT_PROVIDER")
    default_model: str = Field(default="qwen/qwen3-4b", alias="DEFAULT_MODEL")

    # Shorthand for the LM Studio provider. Overridden by AI_PROVIDERS when set.
    lm_studio_base_url: str = Field(
        default="http://localhost:1234/v1", alias="AI_BASE_URL"
    )
    lm_studio_api_key: str = Field(default="lm-studio", alias="AI_API_KEY")

    # Optional persona. Prepended as a system message when the client sends none.
    system_prompt: str = Field(
        default=(
            "You are an AI research assistant for a scientific knowledge-map editor. "
            "Answer concisely and accurately in the user's language. "
            "Do not output chain-of-thought reasoning; answer directly."
        ),
        alias="SYSTEM_PROMPT",
    )

    # Optional JSON list of providers. Example:
    # [{"name":"lm-studio","base_url":"http://localhost:1234/v1",
    #   "api_key":"lm-studio","models":["qwen/qwen3-4b"]}]
    providers_json: str | None = Field(default=None, alias="AI_PROVIDERS")

    # cloud.ru Foundation Models provider.
    # Configured via these constants; a "cloudru" provider is registered
    # automatically when CLOUDRU_API_KEY is set.
    cloudru_api_key: str = Field(default="", alias="CLOUDRU_API_KEY")
    cloudru_model: str = Field(
        default="deepseek-ai/DeepSeek-V4-Flash", alias="CLOUDRU_MODEL"
    )

    # Local GGUF model via llama-cpp-python + HuggingFace Hub.
    # A "local-gguf" provider is registered only when ENVIRONMENT=development
    # (staging/production never expose a locally served model) and HF_MODEL_REPO
    # / HF_GGUF_FILE are set. The model file is downloaded on first use into
    # MODEL_CACHE_DIR.
    model_cache_dir: str = Field(default="./models", alias="MODEL_CACHE_DIR")
    hf_model_repo: str = Field(default="", alias="HF_MODEL_REPO")
    hf_gguf_file: str = Field(default="", alias="HF_GGUF_FILE")
    hugging_face_token: str = Field(default="", alias="HUGGING_FACE_TOKEN")
    local_context_length: int = Field(default=32768, alias="LOCAL_CONTEXT_LENGTH")
    local_n_gpu_layers: int = Field(default=0, alias="LOCAL_N_GPU_LAYERS")
    local_strip_reasoning: bool = Field(default=True, alias="LOCAL_STRIP_REASONING")

    request_timeout: float = Field(default=300.0, alias="AI_REQUEST_TIMEOUT")
    connect_timeout: float = Field(default=15.0, alias="AI_CONNECT_TIMEOUT")
    models_cache_ttl: float = Field(default=60.0, alias="AI_MODELS_CACHE_TTL")

    # Default context window (tokens) reported in GET /v1/models when a provider
    # does not expose its own value. Used by the client to show the token ratio.
    default_context_length: int = Field(default=32000, alias="AI_CONTEXT_LENGTH")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")


settings = Settings()


def _cloudru_provider() -> Provider | None:
    """Build the cloud.ru Foundation Models provider from CLOUDRU_* constants."""
    if not settings.cloudru_api_key:
        return None
    return Provider(
        name="cloudru",
        base_url="https://foundation-models.api.cloud.ru/v1",
        api_key=settings.cloudru_api_key,
        models=[settings.cloudru_model],
        default_model=settings.cloudru_model,
        context_length=128000,
    )


def _local_gguf_provider() -> Provider | None:
    """Build the local GGUF provider (development only) from HF_* constants."""
    if settings.environment != "development":
        return None
    if not settings.hf_model_repo or not settings.hf_gguf_file:
        return None
    short_name = settings.hf_model_repo.rsplit("/", 1)[-1]
    model_id = f"local-gguf/{short_name}"
    return Provider(
        name="local-gguf",
        base_url="local://gguf",
        models=[model_id, short_name],
        default_model=model_id,
        context_length=settings.local_context_length,
        use_local=True,
    )


def _lm_studio_fallback() -> list[Provider]:
    return [
        Provider(
            name="lm-studio",
            base_url=settings.lm_studio_base_url,
            api_key=settings.lm_studio_api_key,
            models=[settings.default_model],
            default_model=settings.default_model,
        )
    ]


def load_providers() -> list[Provider]:
    """Build the provider list from ``AI_PROVIDERS``, the LM Studio defaults,
    the cloud.ru provider configured via ``CLOUDRU_*`` constants and the
    development-only local GGUF provider."""
    providers: list[Provider]
    if settings.providers_json:
        data = json.loads(settings.providers_json)
        providers = [Provider(**item) for item in data]
    elif not settings.cloudru_api_key:
        providers = _lm_studio_fallback()
    else:
        providers = []

    cloudru = _cloudru_provider()
    if cloudru and not any(p.name == "cloudru" for p in providers):
        providers.append(cloudru)

    local = _local_gguf_provider()
    if local and not any(p.name == "local-gguf" for p in providers):
        providers.append(local)

    if not providers:
        providers = _lm_studio_fallback()
    return providers