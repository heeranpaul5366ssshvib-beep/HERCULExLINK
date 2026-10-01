from __future__ import annotations
"""Transformers-backed local adapter.

This adapter is optional and intentionally lightweight: it only attempts to load
transformers when available and never hard-codes a machine-specific path.
"""
from typing import Any, Dict, List, Optional

try:
    from transformers import AutoModelForCausalLM, AutoTokenizer
    _HAS_TRANSFORMERS = True
except Exception:
    AutoModelForCausalLM = None  # type: ignore
    AutoTokenizer = None  # type: ignore
    _HAS_TRANSFORMERS = False

from models.adapters.base_adapter import BaseAdapter


class TransformersAdapter(BaseAdapter):
    """Local adapter using Hugging Face transformers when present."""

    def __init__(self, model_name: str = "hf-internal-testing/tiny-random-gpt2"):
        self.model_name = model_name
        self.tokenizer = None
        self.model = None
        self._available = _HAS_TRANSFORMERS
        if self._available:
            try:
                self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
                self.model = AutoModelForCausalLM.from_pretrained(self.model_name)
            except Exception:
                self._available = False

    def health(self) -> Dict[str, Any]:
        if not _HAS_TRANSFORMERS:
            return {"status": "unavailable", "available": False, "reason": "transformers not installed"}
        if not self._available:
            return {"status": "unavailable", "available": False, "reason": "model could not be loaded"}
        return {"status": "healthy", "available": True, "model": self.model_name}

    def generate(self, prompt: str, model: str | None = None, system: str = "", **kwargs) -> str:
        """Real generate path: delegate to chat (no synthesized fallback)."""
        return self.chat(model=model or self.model_name, prompt=prompt, system=system)

    def chat(self, model: str, prompt: str, system: str = "") -> str:
        if not self._available:
            raise RuntimeError("Transformers adapter is unavailable")
        if self.tokenizer is None or self.model is None:
            raise RuntimeError("Transformers tokenizer/model not initialized")
        combined = f"{system}\n{prompt}" if system else prompt
        inputs = self.tokenizer(combined, return_tensors="pt")
        generated = self.model.generate(**inputs, max_new_tokens=32)
        text = self.tokenizer.decode(generated[0], skip_special_tokens=True)
        return text

    def embeddings(self, model: str, text: str):
        if not self._available:
            raise RuntimeError("Transformers adapter is unavailable")
        if self.tokenizer is None:
            raise RuntimeError("Transformers tokenizer is not initialized")
        return self.tokenizer.encode(text, return_tensors="pt").tolist()[0]
