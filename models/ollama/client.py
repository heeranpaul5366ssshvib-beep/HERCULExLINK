from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Ollama Client
Author: Heeran Paul
License: MIT
--------------------------------------------

Real local-Ollama HTTP client over the standard library (no third-party
dependency). Speaks the Ollama REST API (/api/tags, /api/chat,
/api/embeddings) with configurable timeouts and structured errors:

OllamaConnectionError  server unreachable / refused
OllamaTimeoutError     connect or read past deadline
OllamaModelNotFoundError requested model not installed
OllamaResponseError    malformed / unexpected server reply

The previous fake-stub fallback (which fabricated "[OLLAMA-STUB]"
replies) has been removed: failures raise honestly and surface as
structured ``[HERCULE Error]`` results, never invented text.
"""

import json
import socket
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional


class OllamaError(RuntimeError):
    """Base class for all Ollama client failures."""

    code = "OLLAMA_ERROR"


class OllamaConnectionError(OllamaError):
    """Server unreachable (not running, refused, DNS)."""

    code = "OLLAMA_CONNECTION"


class OllamaTimeoutError(OllamaError):
    """Request exceeded its connect/read deadline."""

    code = "OLLAMA_TIMEOUT"


class OllamaModelNotFoundError(OllamaError):
    """Requested model is not installed on the server (404)."""

    code = "OLLAMA_MODEL_NOT_FOUND"


class OllamaResponseError(OllamaError):
    """Server replied, but the payload was malformed or unexpected."""

    code = "OLLAMA_MALFORMED_RESPONSE"


DEFAULT_TIMEOUT_S = 120.0
CONNECT_TIMEOUT_S = 5.0


class OllamaClient:
    def __init__(self, host: str = "http://127.0.0.1:11434",
                 timeout_s: float = DEFAULT_TIMEOUT_S,
                 connect_timeout_s: float = CONNECT_TIMEOUT_S):
        self.host = (host or "http://127.0.0.1:11434").rstrip("/")
        self.timeout_s = float(timeout_s or DEFAULT_TIMEOUT_S)
        self.connect_timeout_s = float(connect_timeout_s or CONNECT_TIMEOUT_S)

    # --------------------------------------------------
    def _post(self, path: str, payload: Dict[str, Any],
              timeout_s: Optional[float] = None) -> Dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.host + path, data=body,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(
                    request, timeout=timeout_s or self.timeout_s) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise OllamaModelNotFoundError(
                    f"model not found on Ollama server: {payload.get('model')!r}")
            raise OllamaResponseError(
                f"Ollama HTTP {exc.code} on {path}: {exc.reason}")
        except urllib.error.URLError as exc:
            raise OllamaConnectionError(
                f"cannot reach Ollama at {self.host}: {exc.reason}")
        except (socket.timeout, TimeoutError) as exc:
            raise OllamaTimeoutError(
                f"Ollama request to {path} timed out: {exc}")
        except OllamaError:
            raise
        except Exception as exc:
            raise OllamaResponseError(f"Ollama request failed: {exc}")
        try:
            data = json.loads(raw)
        except Exception as exc:
            raise OllamaResponseError(f"Ollama returned non-JSON: {exc}")
        if not isinstance(data, dict):
            raise OllamaResponseError("Ollama returned unexpected JSON shape")
        return data

    def _get(self, path: str) -> Dict[str, Any]:
        try:
            with urllib.request.urlopen(
                    self.host + path, timeout=self.connect_timeout_s) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise OllamaResponseError(
                f"Ollama HTTP {exc.code} on {path}: {exc.reason}")
        except urllib.error.URLError as exc:
            raise OllamaConnectionError(
                f"cannot reach Ollama at {self.host}: {exc.reason}")
        except (socket.timeout, TimeoutError) as exc:
            raise OllamaTimeoutError(
                f"Ollama request to {path} timed out: {exc}")
        except OllamaError:
            raise
        except Exception as exc:
            raise OllamaResponseError(f"Ollama request failed: {exc}")
        try:
            data = json.loads(raw)
        except Exception as exc:
            raise OllamaResponseError(f"Ollama returned non-JSON: {exc}")
        if not isinstance(data, dict):
            raise OllamaResponseError("Ollama returned unexpected JSON shape")
        return data

    # --------------------------------------------------
    def list_models(self) -> List[str]:
        """Names of models installed on the server (never invented)."""
        data = self._get("/api/tags")
        models = data.get("models", [])
        if not isinstance(models, list):
            raise OllamaResponseError("Ollama /api/tags missing 'models' list")
        names = [m.get("name") for m in models
                 if isinstance(m, dict) and m.get("name")]
        return [str(n) for n in names]

    def model_details(self) -> List[Dict[str, Any]]:
        """Raw /api/tags entries (name, size, details, capabilities)."""
        data = self._get("/api/tags")
        models = data.get("models", [])
        if not isinstance(models, list):
            raise OllamaResponseError("Ollama /api/tags missing 'models' list")
        return [dict(m) for m in models if isinstance(m, dict)]

    def exists(self, model: str) -> bool:
        try:
            return str(model) in self.list_models()
        except OllamaError:
            raise
        except Exception as exc:
            raise OllamaResponseError(f"model check failed: {exc}")

    def chat(self, model: str, prompt: str, system: str = "",
             options: Optional[Dict[str, Any]] = None,
             timeout_s: Optional[float] = None,
             keep_alive: str = "15m") -> str:
        if not str(prompt or "").strip():
            raise OllamaResponseError("refusing empty prompt")
        messages: List[Dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload: Dict[str, Any] = {"model": model, "messages": messages,
                                   "stream": False, "keep_alive": keep_alive}
        if options:
            payload["options"] = dict(options)
        data = self._post("/api/chat", payload, timeout_s=timeout_s)
        message = data.get("message")
        if not isinstance(message, dict):
            raise OllamaResponseError("Ollama /api/chat missing 'message' object")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise OllamaResponseError("Ollama /api/chat returned empty content")
        return content

    def chat_vision(self, model: str, prompt: str, images: List[str],
                    system: str = "",
                    options: Optional[Dict[str, Any]] = None,
                    timeout_s: Optional[float] = None,
                    keep_alive: str = "15m") -> str:
        """Chat with base64-encoded images (Ollama vision models).

        Additive v1.1 method for visual perception; existing chat() is
        untouched. ``images`` are base64 PNG/JPEG payloads (no data-URI
        prefix). Failures raise the same structured OllamaError types.
        """
        if not str(prompt or "").strip():
            raise OllamaResponseError("refusing empty prompt")
        if not images or not all(isinstance(i, str) and i.strip() for i in images):
            raise OllamaResponseError("chat_vision requires at least one base64 image")
        user_message: Dict[str, Any] = {"role": "user", "content": prompt,
                                        "images": list(images)}
        messages: List[Dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append(user_message)
        payload: Dict[str, Any] = {"model": model, "messages": messages,
                                   "stream": False, "keep_alive": keep_alive}
        if options:
            payload["options"] = dict(options)
        data = self._post("/api/chat", payload, timeout_s=timeout_s)
        message = data.get("message")
        if not isinstance(message, dict):
            raise OllamaResponseError("Ollama /api/chat missing 'message' object")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise OllamaResponseError("Ollama /api/chat returned empty content")
        return content

    def embeddings(self, model: str, text: str,
                   timeout_s: Optional[float] = None) -> List[float]:
        data = self._post("/api/embeddings",
                          {"model": model, "prompt": text},
                          timeout_s=timeout_s)
        embedding = data.get("embedding")
        if (not isinstance(embedding, list) or not embedding
                or not all(isinstance(x, (int, float)) for x in embedding)):
            raise OllamaResponseError("Ollama /api/embeddings returned no vector")
        return [float(x) for x in embedding]

    def ps(self) -> Any:
        return self._get("/api/ps")
