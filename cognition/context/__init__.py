from __future__ import annotations
"""
============================================
HERCULE AI Operating System
Module: Context Management
============================================
"""

from .context_manager import (
    ContextManager,
    ContextBuilder,
    ContextLayer,
    ProviderType,
    LayerContent,
    StructuredTaskState,
    ContextCheckpoint,
    BuiltContext,
    ContextDiagnostics,
    TokenCounter,
    ToolOutputNormalizer,
    DEFAULT_CONTEXT_BUDGETS,
    LAYER_PRIORITY,
    LAYER_MAX_TOKENS,
    CONTEXT_SCHEMA_VERSION,
    create_context_manager,
)

__all__ = [
    "ContextManager",
    "ContextBuilder",
    "ContextLayer",
    "ProviderType",
    "LayerContent",
    "StructuredTaskState",
    "ContextCheckpoint",
    "ContextDiagnostics",
    "BuiltContext",
    "TokenCounter",
    "ToolOutputNormalizer",
    "DEFAULT_CONTEXT_BUDGETS",
    "LAYER_PRIORITY",
    "LAYER_MAX_TOKENS",
    "CONTEXT_SCHEMA_VERSION",
    "create_context_manager",
]