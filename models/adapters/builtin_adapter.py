from __future__ import annotations
"""Built-in local adapter registration (v2).

Thin alias: the canonical implementation is
models.builtin.provider.BuiltinLocalProvider (same generation
contract as the Ollama adapter). Importing this module never starts
inference or downloads anything.
"""

from models.builtin.provider import BuiltinLocalProvider, BuiltinUnavailable

__all__ = ["BuiltinAdapter", "BuiltinLocalProvider", "BuiltinUnavailable"]


class BuiltinAdapter(BuiltinLocalProvider):
    """Router-facing name for the built-in local provider."""

    name = "builtin"
