"""
Smart Repair Analyzers

Every analyzer inspects one aspect of the
project and reports issues.

Analyzers NEVER modify files.
"""

from .code_analyzer import CodeAnalyzer

__all__ = [
    "CodeAnalyzer",
]