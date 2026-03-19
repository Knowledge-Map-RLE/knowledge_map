"""Базовый класс для XML→Markdown конвертеров."""
from abc import ABC, abstractmethod
from typing import Dict, Optional

ImageUrls = Dict[str, str]


class BaseXmlConverter(ABC):
    """Абстрактный конвертер XML → Markdown."""

    @abstractmethod
    def convert(self, xml_bytes: bytes, **kwargs) -> str:
        """Конвертировать XML в Markdown.

        Args:
            xml_bytes: XML контент в байтах
            **kwargs: Дополнительные параметры (например, image_urls)

        Returns:
            Markdown-строка или "" при ошибке
        """
        ...
