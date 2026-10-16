"""Совместимое имя для единого сервиса преобразования PDF."""

from .indra_conversion_service import ConversionService

PDFConversionService = ConversionService

__all__ = ["PDFConversionService"]