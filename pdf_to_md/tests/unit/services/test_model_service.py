"""Проверки единственной модели и production-блокировки лицензии."""

import pytest

from src.core.config import settings
from src.core.types import ModelStatus
from src.services.model_service import ModelService


@pytest.mark.unit
def test_registry_exposes_only_neutral_default_model():
    service = ModelService()

    assert list(service.get_available_models()) == ["default"]
    assert service.get_default_model() == "default"
    assert service.get_model("default") is not None
    assert service.get_model("other") is None
    assert service.get_model_info("default").status == ModelStatus.ENABLED.value


@pytest.mark.unit
def test_default_model_cannot_be_disabled():
    service = ModelService()

    assert service.disable_model("default") is False
    assert service.validate_model("default") is True


@pytest.mark.unit
def test_production_requires_explicit_license_review(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "indra_license_reviewed", False)

    with pytest.raises(RuntimeError, match="INDRA_LICENSE_REVIEWED=true"):
        ModelService()
