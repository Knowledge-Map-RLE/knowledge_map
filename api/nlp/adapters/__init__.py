"""
Adapters for converting NLP tool outputs to unified format.
"""

from .base_adapter import BaseAdapter
from .universal_dependencies_mapper import UniversalDependenciesMapper
from .udpipe_adapter import UDPipeAdapter

__all__ = ['BaseAdapter', 'UniversalDependenciesMapper', 'UDPipeAdapter']
