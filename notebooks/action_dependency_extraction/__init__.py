"""
Action Dependency Extraction Package

Модуль для извлечения зависимостей между действиями из научных текстов
и построения направленного ациклического графа (DAG).
"""

from .models import Action, Dependency
from .extractors import ActionExtractor, DependencyExtractor
from .builders import DAGBuilder
from .exporters import ResultExporter

__version__ = "2.1.0"
__all__ = [
    'Action',
    'Dependency',
    'ActionExtractor',
    'DependencyExtractor',
    'DAGBuilder',
    'ResultExporter',
]
