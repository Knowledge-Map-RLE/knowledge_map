"""Logging configuration for PDF to Markdown service."""

import logging
import sys
from pathlib import Path
from typing import Optional

from observability import setup_logging as obs_setup_logging

from .config import settings


def setup_logging(
    log_level: Optional[str] = None,
    log_file: Optional[Path] = None,
    service_name: Optional[str] = None
) -> logging.Logger:
    """Setup logging configuration, delegating to the shared observability package."""
    name = service_name or settings.service_name
    obs_setup_logging(service_name=name)
    if log_level:
        logging.getLogger(name).setLevel(getattr(logging, log_level.upper()))
    return logging.getLogger(name)


def get_logger(name: str) -> logging.Logger:
    """Get logger instance for a specific module."""
    return logging.getLogger(f"{settings.service_name}.{name}")