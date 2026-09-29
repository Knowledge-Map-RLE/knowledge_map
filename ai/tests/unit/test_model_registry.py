from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "shared" / "model_registry"))

from model_registry import ModelRegistry, ModelRegistryError  # noqa: E402


REGISTRY = REPO_ROOT / "config" / "models.toml"


def test_qwen8_profile_uses_requested_maximum_context() -> None:
    resolved = ModelRegistry(REGISTRY).profile("local_qwen3_8b")

    assert resolved.model_id == "qwen/qwen3-8b"
    assert resolved.profile.context_length == 40960
    assert resolved.profile.max_tokens < resolved.profile.context_length


def test_roles_resolve_to_a_profile() -> None:
    registry = ModelRegistry(REGISTRY)

    assert registry.profile(role="ui_chat").profile_name == "openai_gpt6_luna"
    assert registry.profile(role="article_extraction").profile_name == "openai_gpt6_luna"
    assert registry.profile(role="knowledge_core").profile_name == "openai_gpt6_luna"


def test_openai_gpt6_luna_uses_maximum_model_limits_and_reasoning() -> None:
    resolved = ModelRegistry(REGISTRY).profile("openai_gpt6_luna")

    assert resolved.provider.kind == "openai_responses"
    assert resolved.model_id == "gpt-6-luna"
    assert resolved.profile.context_length == 1_050_000
    assert resolved.profile.max_tokens == 128_000
    assert resolved.profile.reasoning_effort == "max"


def test_invalid_active_profile_fails_fast() -> None:
    registry = ModelRegistry(REGISTRY)
    registry._data["active_profile"] = "missing"

    try:
        registry._validate()
    except ModelRegistryError as exc:
        assert "active_profile" in str(exc)
    else:
        raise AssertionError("invalid active profile must fail validation")
