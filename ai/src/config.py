"""Configuration for the AI Agent microservice.

The service is an OpenAI-compatible chat gateway. It knows nothing about specific
models: it forwards ``/v1/chat/completions`` requests to one of the configured
providers (OpenAI Responses API, OpenAI-compatible services, or a local GGUF
model via llama-cpp-python) and streams the reply back in OpenAI format.

Environment split
-----------------
The service reads ``.env.<ENVIRONMENT>`` when ``ENVIRONMENT`` is set in the
process environment (or defaults to ``development`` locally), falling back to
``.env``. Example: ``ai/.env.development`` holds the development provider
configuration, ``ai/.env.production`` would hold production secrets.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv
from model_registry import ModelRegistry


class Provider(BaseModel):
    """An upstream provider (OpenAI Responses, compatible HTTP, local GGUF, ...).

    All HTTP-based providers use ``HttpProviderClient`` (OpenAI-compatible).

    ``use_local`` marks a provider implemented by ``LocalGGUFProviderClient``
    (llama-cpp-python + HuggingFace Hub).
    """

    name: str
    base_url: str
    kind: str = "openai_compatible"
    api_key: str | None = None
    models: list[str] = Field(default_factory=list)
    generation_options: dict[str, dict] = Field(default_factory=dict)
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


_ENV_FILE = _resolve_env_file()
if _ENV_FILE:
    # The shared model registry reads provider credentials from os.environ.
    # pydantic-settings reads env files without populating os.environ, so load
    # the selected service env file first; never override deployment env vars.
    load_dotenv(_ENV_FILE, override=False)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    host: str = Field(default="0.0.0.0", alias="AI_HOST")
    port: int = Field(default=50059, alias="AI_PORT")

    # Deployment environment: development / staging / production.
    environment: str = Field(default="development", alias="ENVIRONMENT")

    # Shared model registry. The registry is the source of truth for providers,
    # model ids, profiles and generation defaults.
    model_config_path: str = Field(default="", alias="MODEL_CONFIG_PATH")
    model_profile: str = Field(default="", alias="MODEL_PROFILE")

    # Legacy endpoint/key fields kept for compatibility with existing env files.
    # The shared model registry is authoritative for provider routing.
    lm_studio_base_url: str = Field(
        default="http://127.0.0.1:1234/v1", alias="AI_BASE_URL"
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

    # Legacy cloud.ru values remain readable for migration diagnostics only.
    cloudru_api_key: str = Field(default="", alias="CLOUDRU_API_KEY")

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
    default_context_length: int = Field(default=1050000, alias="AI_CONTEXT_LENGTH")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")


settings = Settings()
model_registry = ModelRegistry(settings.model_config_path or None)


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


def load_providers() -> list[Provider]:
    """Build providers from the shared model registry.

    Every configured provider is visible, including cloud.ru without a key;
    calls using such a profile fail explicitly at the upstream boundary.
    """
    active = model_registry.profile(settings.model_profile or None)
    providers: list[Provider] = []
    for provider in model_registry.providers:
        profiles = [p for p in model_registry.profiles if p.provider == provider.name]
        if not profiles:
            continue
        default_profile = next(
            (profile for profile in profiles if profile.name == active.profile_name),
            profiles[0],
        )
        providers.append(
            Provider(
                name=provider.name,
                base_url=provider.base_url,
                kind=provider.kind,
                api_key=provider.api_key,
                models=[profile.model_id for profile in profiles],
                generation_options={
                    profile.model_id: {
                        "reasoning_effort": profile.reasoning_effort,
                        "max_tokens": profile.max_tokens,
                    }
                    for profile in profiles
                },
                default_model=default_profile.model_id,
                context_length=default_profile.context_length,
            )
        )

    local = _local_gguf_provider()
    if local and not any(p.name == local.name for p in providers):
        providers.append(local)
    if not providers:
        raise ValueError("Model registry has no provider with a configured model profile")
    return providers
