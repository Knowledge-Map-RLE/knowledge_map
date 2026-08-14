"""Configuration for the AI Agent microservice.

The service is an OpenAI-compatible chat gateway. It knows nothing about specific
models: it forwards ``/v1/chat/completions`` requests to one of the configured
providers (LM Studio during development, DeepSeek Pro/Flash later) and streams
the reply back in OpenAI format.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Provider(BaseModel):
    """An OpenAI-compatible upstream provider (LM Studio, DeepSeek, ...)."""

    name: str
    base_url: str
    api_key: str | None = None
    models: list[str] = Field(default_factory=list)
    default_model: str | None = None
    context_length: int | None = None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    host: str = Field(default="0.0.0.0", alias="AI_HOST")
    port: int = Field(default=50054, alias="AI_PORT")

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

    # Yandex AI Studio / Yandex Cloud Foundation Models provider.
    # Configured via these constants; a "yandex-ai" provider is registered
    # automatically when YANDEX_CLOUD_API_KEY is set.
    yandex_cloud_folder: str = Field(default="", alias="YANDEX_CLOUD_FOLDER")
    yandex_cloud_api_key: str = Field(default="", alias="YANDEX_CLOUD_API_KEY")
    yandex_cloud_model: str = Field(
        default="deepseek-v4-flash/latest", alias="YANDEX_CLOUD_MODEL"
    )

    request_timeout: float = Field(default=300.0, alias="AI_REQUEST_TIMEOUT")
    connect_timeout: float = Field(default=15.0, alias="AI_CONNECT_TIMEOUT")
    models_cache_ttl: float = Field(default=60.0, alias="AI_MODELS_CACHE_TTL")

    # Default context window (tokens) reported in GET /v1/models when a provider
    # does not expose its own value. Used by the client to show the token ratio.
    default_context_length: int = Field(default=32000, alias="AI_CONTEXT_LENGTH")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")


settings = Settings()


def _yandex_provider() -> Provider | None:
    """Build the Yandex AI Studio / Cloud provider from YANDEX_CLOUD_* constants."""
    if not settings.yandex_cloud_api_key or not settings.yandex_cloud_folder:
        return None
    model_uri = (
        f"gpt://{settings.yandex_cloud_folder.rstrip('/')}/"
        f"{settings.yandex_cloud_model.lstrip('/')}"
    )
    return Provider(
        name="yandex-ai",
        base_url="https://ai.api.cloud.yandex.net/v1",
        api_key=settings.yandex_cloud_api_key,
        models=[model_uri],
        default_model=model_uri,
        context_length=128000,
    )


def load_providers() -> list[Provider]:
    """Build the provider list from ``AI_PROVIDERS``, the LM Studio defaults,
    or the Yandex provider configured via ``YANDEX_CLOUD_*`` constants."""
    providers: list[Provider]
    if settings.providers_json:
        data = json.loads(settings.providers_json)
        providers = [Provider(**item) for item in data]
    elif not settings.yandex_cloud_api_key:
        providers = [
            Provider(
                name=settings.default_provider,
                base_url=settings.lm_studio_base_url,
                api_key=settings.lm_studio_api_key,
                models=[settings.default_model],
                default_model=settings.default_model,
            )
        ]
    else:
        providers = []

    yandex = _yandex_provider()
    if yandex and not any(p.name == "yandex-ai" for p in providers):
        providers.append(yandex)

    if not providers:
        providers = [
            Provider(
                name="lm-studio",
                base_url=settings.lm_studio_base_url,
                api_key=settings.lm_studio_api_key,
                models=["qwen/qwen3-4b"],
                default_model="qwen/qwen3-4b",
            )
        ]
    return providers
