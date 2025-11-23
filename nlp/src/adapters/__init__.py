"""
Adapters for converting NLP tool outputs to unified format.
"""

from src.adapters.base_adapter import BaseAdapter
from src.adapters.universal_dependencies_mapper import UniversalDependenciesMapper
from src.adapters.udpipe_adapter import UDPipeAdapter

__all__ = ['BaseAdapter', 'UniversalDependenciesMapper', 'UDPipeAdapter']
