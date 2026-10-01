from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Vision Providers (v1.1)
Author: Heeran Paul
License: MIT
--------------------------------------------

Provider-neutral visual perception over LOCAL vision-capable models
only: no cloud, no API keys. Models are discovered dynamically from
the Ollama server (capabilities + known vision name fragments); when
no vision model is installed the provider reports VISION UNAVAILABLE
with a reason — observations are never fabricated.
"""

import base64
import json
from typing import Any, Dict, List, Optional

from perception.vision.result import validate_observation


class VisionUnavailable(RuntimeError):
    """Raised when visual perception genuinely cannot run here."""


# Name fragments identifying locally runnable vision-capable models.
# Matched case-insensitively against installed Ollama model names.
KNOWN_VISION_FRAGMENTS = (
    "llava", "moondream", "bakllava", "llama3.2-vision", "qwen2-vl",
    "qwen-vl", "minicpm-v", "granite-vision", "mistral-small3",
    "gemma3-vision", "qwen3-vl",
)


class VisionProvider:
    """Vision engine interface (replaceable)."""

    name = "base"

    def available(self) -> Dict[str, Any]:
        raise NotImplementedError

    def describe(self, image_b64: str, mime: str, prompt: str,
                 width: int = 0, height: int = 0,
                 source: str = "image-file") -> Dict[str, Any]:
        """Return a VALIDATED observation dict (never raw model output)."""
        raise NotImplementedError


def _looks_like_vision(name: str, capabilities: List[str] | None = None) -> bool:
    lowered = str(name or "").lower()
    if any(frag in lowered for frag in KNOWN_VISION_FRAGMENTS):
        return True
    for cap in capabilities or []:
        if str(cap).strip().lower() == "vision":
            return True
    return False


class OllamaVisionProvider(VisionProvider):
    """Local vision via Ollama /api/chat with base64 images."""

    name = "ollama"

    def __init__(self, model: str = "", timeout_s: float = 60.0):
        self.model = str(model or "").strip()
        self.timeout_s = float(timeout_s or 60.0)
        self._probe: Optional[Dict[str, Any]] = None

    def _client(self):  # lazy: no import cost until first use
        from models.ollama.client import OllamaClient

        return OllamaClient(timeout_s=self.timeout_s)

    def vision_models(self) -> List[str]:
        """Installed vision-capable model names (never invented)."""
        client = self._client()
        try:
            details = client.model_details()
        except Exception:
            details = []
        found: List[str] = []
        for entry in details:
            name = str((entry or {}).get("name", "") or "")
            caps = []
            info = (entry or {}).get("details") or {}
            if isinstance(info, dict):
                caps = info.get("capabilities") or []
            if name and _looks_like_vision(name, list(caps or [])):
                found.append(name)
        if found:
            return found
        # Fallback: /api/tags without details — match names only.
        try:
            names = client.list_models()
        except Exception:
            names = []
        return [n for n in names if _looks_like_vision(n)]

    def available(self) -> Dict[str, Any]:
        if self._probe is not None:
            return dict(self._probe)
        try:
            models = self.vision_models()
        except Exception as exc:
            self._probe = {"available": False,
                           "reason": f"vision discovery failed: {exc}"}
            return dict(self._probe)
        if not models:
            self._probe = {"available": False,
                           "reason": ("VISION UNAVAILABLE: no vision-capable model "
                                      "installed (e.g. `ollama pull moondream`)")}
            return dict(self._probe)
        if self.model:
            if self.model not in models:
                self._probe = {"available": False,
                               "reason": (f"vision model not installed: {self.model!r} "
                                          f"(installed vision: {models})")}
                return dict(self._probe)
            chosen = self.model
        else:
            chosen = models[0]
        self._probe = {"available": True, "model": chosen,
                       "vision_models": models}
        return dict(self._probe)

    def describe(self, image_b64: str, mime: str, prompt: str,
                 width: int = 0, height: int = 0,
                 source: str = "image-file") -> Dict[str, Any]:
        probe = self.available()
        if not probe.get("available"):
            raise VisionUnavailable(str(probe.get("reason", "VISION UNAVAILABLE")))
        if not str(image_b64 or "").strip():
            raise ValueError("empty image: nothing to analyze")
        model = str(probe.get("model", "") or "")
        instruction = (
            str(prompt or "Describe this image.").strip() + "\n\n"
            "Reply as compact JSON only: "
            '{"description": "...", "detected_text": [...], '
            '"regions": [{"label": "...", "x": 0.0, "y": 0.0, "width": 0.0, '
            '"height": 0.0, "confidence": 0.0}], "objects": [...], '
            '"confidence": 0.0}. Boxes are 0..1 relative. '
            "Never invent text that is not visible."
        )
        try:
            from models.adapters.ollama_adapter import OllamaAdapter

            adapter = OllamaAdapter(timeout_s=self.timeout_s)
            raw = adapter.chat_vision(model=model, prompt=instruction,
                                      images=[image_b64],
                                      timeout_s=self.timeout_s)
        except Exception as exc:
            raise VisionUnavailable(f"vision inference failed: {exc}")
        payload = _parse_model_json(raw)
        payload["source"] = source
        payload["model"] = model
        payload["width"] = int(width or 0)
        payload["height"] = int(height or 0)
        return validate_observation(payload).as_dict()


def _parse_model_json(raw: str) -> Dict[str, Any]:
    """Parse model output strictly: JSON object, or description-only wrap.

    A JSON object is validated downstream. Anything else becomes a
    description-only observation (no invented text/regions/objects) so
    raw output never reaches execution unstructured.
    """
    text = str(raw or "").strip()
    if not text:
        raise ValueError("malformed vision output: empty model reply")
    # Strip code fences when the model wraps JSON in markdown.
    if text.startswith("```"):
        lines = text.splitlines()
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        text = "\n".join(lines).strip()
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except Exception as exc:
            raise ValueError(f"malformed vision output: invalid JSON ({exc})")
        if not isinstance(data, dict):
            raise ValueError("malformed vision output: JSON is not an object")
        data.setdefault("detected_text", [])
        data.setdefault("regions", [])
        data.setdefault("objects", [])
        data.setdefault("confidence", 0.5)
        return dict(data)
    # Free-text reply: description only, moderate confidence, no invented
    # structure. Downstream validation still enforces source/model.
    return {"description": text[:2000], "detected_text": [],
            "regions": [], "objects": [], "confidence": 0.5}


def get_vision_provider(name: str = "ollama", **kwargs: Any) -> VisionProvider:
    providers = {"ollama": OllamaVisionProvider}
    key = str(name or "ollama").strip().lower()
    if key not in providers:
        raise ValueError(f"unknown vision provider: {name!r} "
                         f"(available: {sorted(providers)})")
    return providers[key](**kwargs)
