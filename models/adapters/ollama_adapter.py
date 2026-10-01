from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Ollama Adapter
Author: Heeran Paul
License: MIT
--------------------------------------------

Adapter over the real local-Ollama client: model discovery, health
reporting installed models, generation with configurable timeouts and
options. Failures propagate as structured OllamaError exceptions —
never fabricated text.
"""

import os
from typing import Any, Dict, List, Optional

from models.adapters.base_adapter import BaseAdapter
from models.ollama.client import OllamaClient


def _default_host() -> str:
    return os.environ.get("HERCULE_OLLAMA_HOST", "http://127.0.0.1:11434")


class OllamaAdapter(BaseAdapter):

    # Bounded replies by default: long rambles waste latency and can
    # outlast operator timeouts. Callers may override per call via
    # options={"num_predict": N} (None disables the cap explicitly).
    DEFAULT_OPTIONS: Dict[str, Any] = {"num_predict": 512}

    def __init__(self, host: Optional[str] = None,
                 timeout_s: float = 120.0,
                 options: Optional[Dict[str, Any]] = None):
        self.host = host or _default_host()
        self.timeout_s = float(timeout_s or 120.0)
        self.options = dict(self.DEFAULT_OPTIONS)
        if options:
            self.options.update(options)
        if self.options.get("num_predict") is None:
            self.options.pop("num_predict", None)
        self.client = OllamaClient(host=self.host, timeout_s=self.timeout_s)

    def health(self):
        try:
            models = self.client.list_models()
            return {"status": "healthy", "available": True,
                    "models": models, "host": self.host}
        except Exception as exc:
            return {"status": "unavailable", "available": False,
                    "reason": f"{type(exc).__name__}: {exc}", "host": self.host}

    def discover_models(self) -> List[str]:
        """Installed model names from the server (never invented)."""
        return self.client.list_models()

    def generate(
        self,
        prompt: str,
        model: str | None = None,
        system: str = "",
        timeout_s: Optional[float] = None,
        **kwargs,
    ):
        """Real generate path: delegate to chat (no synthesized fallback)."""
        return self.chat(model=model, prompt=prompt, system=system,
                         timeout_s=timeout_s, **kwargs)

    def chat(
        self,
        model: str | None = None,
        prompt: str | None = None,
        system: str = "",
        messages: Optional[List[Dict[str, Any]]] = None,
        timeout_s: Optional[float] = None,
        **kwargs,
    ):
        if prompt is None and messages:
            prompt = "\n".join(item.get("content", "") for item in messages if isinstance(item, dict))
        if model is None:
            # No machine-specific default: resolve from installed models.
            installed = self.discover_models()
            if not installed:
                from models.ollama.client import OllamaResponseError
                raise OllamaResponseError("no models installed on Ollama server")
            model = installed[0]
        options = dict(self.options)
        if isinstance(kwargs.get("options"), dict):
            options.update(kwargs["options"])
        return self.client.chat(
            model=model,
            prompt=prompt or "",
            system=system,
            options=options or None,
            timeout_s=timeout_s or self.timeout_s,
        )

    def chat_vision(
        self,
        model: str | None = None,
        prompt: str = "",
        images: Optional[List[str]] = None,
        system: str = "",
        timeout_s: Optional[float] = None,
        **kwargs,
    ):
        """Vision chat over a local vision-capable model (additive v1.1)."""
        if model is None:
            raise ValueError("chat_vision requires an explicit vision model name")
        options = dict(self.options)
        if isinstance(kwargs.get("options"), dict):
            options.update(kwargs["options"])
        return self.client.chat_vision(
            model=model,
            prompt=prompt or "",
            images=list(images or []),
            system=system,
            options=options or None,
            timeout_s=timeout_s or self.timeout_s,
        )

    def embeddings(
        self,
        model: str,
        text: str,
    ):
        return self.client.embeddings(
            model=model,
            text=text,
        )
