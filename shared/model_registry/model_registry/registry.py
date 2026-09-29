"""Validated, shared model profiles used by all Knowledge Map services.

Credentials remain outside the TOML file. Providers refer to an environment
variable containing their API key, while profiles keep routing and generation
metadata.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ModelRegistryError(ValueError):
    """Raised when the model registry is missing or inconsistent."""


@dataclass(frozen=True)
class ProviderProfile:
    name: str
    kind: str
    base_url: str
    api_key_env: str | None
    api_key: str


@dataclass(frozen=True)
class ModelProfile:
    name: str
    provider: str
    model_key: str
    model_id: str
    display_name: str
    context_length: int
    max_tokens: int
    temperature: float
    top_p: float | None
    top_k: int | None
    strip_reasoning: bool
    reasoning_effort: str | None
    roles: tuple[str, ...]


@dataclass(frozen=True)
class ResolvedModel:
    profile: ModelProfile
    provider: ProviderProfile

    @property
    def profile_name(self) -> str:
        return self.profile.name

    @property
    def model_id(self) -> str:
        return self.profile.model_id


class ModelRegistry:
    """Read-only registry with explicit profile and role resolution."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = self._resolve_path(path)
        self._data = self._load_file(self.path)
        self._providers = self._parse_providers(self._data)
        self._profiles = self._parse_profiles(self._data)
        self._roles = self._parse_roles(self._data)
        self._validate()

    @staticmethod
    def _resolve_path(path: str | Path | None) -> Path:
        configured = path or os.getenv("MODEL_CONFIG_PATH")
        if configured:
            return Path(configured).expanduser().resolve()
        candidates = [
            Path.cwd() / "config" / "models.toml",
            # shared/model_registry/model_registry/registry.py -> repository root.
            Path(__file__).resolve().parents[3] / "config" / "models.toml",
        ]
        for candidate in candidates:
            if candidate.is_file():
                return candidate.resolve()
        return candidates[0].resolve()

    @staticmethod
    def _load_file(path: Path) -> dict[str, Any]:
        if not path.is_file():
            raise ModelRegistryError(f"Model registry does not exist: {path}")
        try:
            with path.open("rb") as stream:
                data = tomllib.load(stream)
        except tomllib.TOMLDecodeError as exc:
            raise ModelRegistryError(f"Invalid TOML model registry {path}: {exc}") from exc
        if data.get("version") != 1:
            raise ModelRegistryError("Unsupported model registry version; expected version = 1")
        return data

    @staticmethod
    def _parse_providers(data: dict[str, Any]) -> dict[str, ProviderProfile]:
        providers: dict[str, ProviderProfile] = {}
        for name, raw in (data.get("providers") or {}).items():
            if not isinstance(raw, dict):
                raise ModelRegistryError(f"Provider '{name}' must be a table")
            api_key_env = str(raw["api_key_env"]) if raw.get("api_key_env") else None
            providers[name] = ProviderProfile(
                name=name,
                kind=str(raw.get("kind", "openai_compatible")),
                base_url=str(raw.get("base_url", "")).rstrip("/"),
                api_key_env=api_key_env,
                api_key=os.getenv(api_key_env, "") if api_key_env else "",
            )
        return providers

    @staticmethod
    def _parse_profiles(data: dict[str, Any]) -> dict[str, ModelProfile]:
        profiles: dict[str, ModelProfile] = {}
        providers = data.get("providers") or {}
        for name, raw in (data.get("profiles") or {}).items():
            if not isinstance(raw, dict):
                raise ModelRegistryError(f"Profile '{name}' must be a table")
            provider_name = str(raw.get("provider", ""))
            model_key = str(raw.get("model", ""))
            provider_models = (providers.get(provider_name) or {}).get("models") or {}
            model = provider_models.get(model_key)
            if not isinstance(model, dict):
                raise ModelRegistryError(
                    f"Profile '{name}' references unknown model "
                    f"'{provider_name}/{model_key}'"
                )
            profiles[name] = ModelProfile(
                name=name,
                provider=provider_name,
                model_key=model_key,
                model_id=str(model.get("id", "")),
                display_name=str(model.get("display_name", name)),
                context_length=int(raw.get("context_length", model.get("context_length", 8192))),
                max_tokens=int(raw.get("max_tokens", model.get("max_tokens", 4096))),
                temperature=float(raw.get("temperature", model.get("temperature", 0.1))),
                top_p=(float(raw["top_p"]) if raw.get("top_p") is not None else None),
                top_k=(int(raw["top_k"]) if raw.get("top_k") is not None else None),
                strip_reasoning=bool(raw.get("strip_reasoning", model.get("strip_reasoning", True))),
                reasoning_effort=(
                    str(raw.get("reasoning_effort", model.get("reasoning_effort"))).strip()
                    if raw.get("reasoning_effort", model.get("reasoning_effort"))
                    else None
                ),
                roles=tuple(str(role) for role in (raw.get("roles") or [])),
            )
        return profiles

    @staticmethod
    def _parse_roles(data: dict[str, Any]) -> dict[str, str]:
        roles = data.get("roles") or {}
        if not isinstance(roles, dict):
            raise ModelRegistryError("'roles' must be a table")
        return {str(role): str(profile) for role, profile in roles.items()}

    def _validate(self) -> None:
        supported_reasoning_efforts = {
            "none", "minimal", "low", "medium", "high", "xhigh", "max",
        }
        if not self._providers:
            raise ModelRegistryError("Model registry must define at least one provider")
        for provider in self._providers.values():
            if not provider.base_url:
                raise ModelRegistryError(f"Provider '{provider.name}' has empty base_url")
        if not self._profiles:
            raise ModelRegistryError("Model registry must define at least one profile")
        for profile in self._profiles.values():
            if profile.provider not in self._providers:
                raise ModelRegistryError(
                    f"Profile '{profile.name}' references unknown provider '{profile.provider}'"
                )
            if not profile.model_id:
                raise ModelRegistryError(f"Profile '{profile.name}' has empty model id")
            if profile.context_length <= 0:
                raise ModelRegistryError(f"Profile '{profile.name}' has invalid context_length")
            if profile.max_tokens <= 0 or profile.max_tokens >= profile.context_length:
                raise ModelRegistryError(
                    f"Profile '{profile.name}' must have 0 < max_tokens < context_length"
                )
            if profile.reasoning_effort and profile.reasoning_effort not in supported_reasoning_efforts:
                raise ModelRegistryError(
                    f"Profile '{profile.name}' has unsupported reasoning_effort "
                    f"'{profile.reasoning_effort}'"
                )
        active = self._data.get("active_profile")
        if active and str(active) not in self._profiles:
            raise ModelRegistryError(f"Unknown active_profile '{active}'")
        for role, profile in self._roles.items():
            if profile not in self._profiles:
                raise ModelRegistryError(
                    f"Role '{role}' references unknown profile '{profile}'"
                )

    @property
    def providers(self) -> tuple[ProviderProfile, ...]:
        return tuple(self._providers.values())

    @property
    def profiles(self) -> tuple[ModelProfile, ...]:
        return tuple(self._profiles.values())

    @property
    def active_profile_name(self) -> str:
        override = os.getenv("MODEL_PROFILE", "").strip()
        name = override or str(self._data.get("active_profile", "")).strip()
        if not name:
            raise ModelRegistryError("No active model profile configured")
        return name

    def profile(self, name: str | None = None, *, role: str | None = None) -> ResolvedModel:
        selected = (name or "").strip()
        if not selected and role:
            selected = os.getenv(f"MODEL_PROFILE_{role.upper()}", "").strip()
            selected = selected or self._roles.get(role, "")
        selected = selected or self.active_profile_name
        profile = self._profiles.get(selected)
        if profile is None:
            raise ModelRegistryError(f"Unknown model profile '{selected}'")
        return ResolvedModel(profile=profile, provider=self._providers[profile.provider])

    def resolve(self, value: str | None, *, role: str | None = None) -> ResolvedModel:
        """Resolve a profile name, or an exact model id during migration."""
        requested = (value or "").strip()
        if not requested or requested == "default":
            return self.profile(role=role)
        if requested in self._profiles:
            return self.profile(requested)
        matches = [profile for profile in self._profiles.values() if profile.model_id == requested]
        if len(matches) == 1:
            return self.profile(matches[0].name)
        if len(matches) > 1:
            raise ModelRegistryError(
                f"Model id '{requested}' maps to multiple profiles; use a profile name"
            )
        raise ModelRegistryError(f"Unknown model profile or model id '{requested}'")
