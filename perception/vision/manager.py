from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Vision Manager (v1.1)
Author: Heeran Paul
License: MIT
--------------------------------------------

Explicit, read-only visual perception. Analysis runs ONLY when the
operator (UI button, typed/voice command, ability call) requests it —
never continuously, never on UI refresh. Images are bounded (byte +
dimension caps); oversized inputs are refused honestly instead of
being silently downscaled by an unverified path.

Sources: screenshot (Windows, when capturable), image-file (workspace
sandbox only), camera (future adapter interface, unavailable by
default). OCR is separated from general visual reasoning: pytesseract
is used when installed, otherwise OCR reports unavailable while the
vision-model description path still works.
"""

import base64
import struct
import threading
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from perception.vision.config import VisionConfig, load_vision_config
from perception.vision.provider import (
    VisionProvider,
    VisionUnavailable,
    get_vision_provider,
)
from perception.vision.result import validate_observation


def image_dimensions(data: bytes) -> Tuple[int, int, str]:
    """Best-effort (width, height, mime) from PNG/JPEG headers (stdlib).

    Returns (0, 0, mime) when dimensions are unreadable; mime sniffing
    still works so the vision model can try. BMP/GIF/WebP report mime
    with (0, 0) dims (passed through, never fabricated).
    """
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        try:
            w, h = struct.unpack(">II", data[16:24])
            return int(w), int(h), "image/png"
        except Exception:
            return 0, 0, "image/png"
    if data[:2] == b"\xff\xd8":
        mime = "image/jpeg"
        try:
            pos = 2
            while pos + 4 <= len(data):
                if data[pos] != 0xFF:
                    break
                marker = data[pos + 1]
                if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                    pos += 2
                    continue
                if pos + 4 > len(data):
                    break
                length = struct.unpack(">H", data[pos + 2:pos + 4])[0]
                if marker in (0xC0, 0xC1, 0xC2) and pos + 9 <= len(data):
                    h = struct.unpack(">H", data[pos + 5:pos + 7])[0]
                    w = struct.unpack(">H", data[pos + 7:pos + 9])[0]
                    return int(w), int(h), mime
                pos += 2 + length
        except Exception:
            pass
        return 0, 0, mime
    if data[:2] == b"BM":
        return 0, 0, "image/bmp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return 0, 0, "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return 0, 0, "image/webp"
    return 0, 0, "application/octet-stream"


def workspace_image_path(path: str) -> Path:
    """Resolve an image path inside the file workspace sandbox."""
    cleaned = str(path or "").strip().strip('"').strip("'")
    if not cleaned:
        raise ValueError("no image path specified")
    try:
        from system.paths import is_frozen, user_data_dir

        workspace = user_data_dir() / "workspace" if is_frozen() else Path.cwd()
        if is_frozen():
            workspace.mkdir(parents=True, exist_ok=True)
    except Exception:
        workspace = Path.cwd()
    candidate = Path(cleaned)
    if candidate.is_absolute():
        raise ValueError(f"path escapes workspace sandbox: {path!r}")
    if ".." in candidate.parts:
        raise ValueError(f"path escapes workspace sandbox: {path!r}")
    target = (workspace / candidate).resolve()
    try:
        target.relative_to(workspace.resolve())
    except ValueError:
        raise ValueError(f"path escapes workspace sandbox: {path!r}")
    return target


class CameraAdapter:
    """Future camera input hook (unavailable by default)."""

    def capture(self) -> bytes:
        raise VisionUnavailable("camera input unavailable (no camera adapter configured)")


class VisionManager:
    """Explicit visual analysis over a VisionProvider (read-only)."""

    def __init__(self, config: Optional[VisionConfig] = None,
                 provider: Optional[VisionProvider] = None,
                 camera: Optional[CameraAdapter] = None):
        self.config = config or load_vision_config()
        self._provider = provider
        self.camera = camera or CameraAdapter()
        self._lock = threading.Lock()
        self._state = "READY"
        self._last_observation: Optional[Dict[str, Any]] = None
        self._last_error = ""

    # --------------------------------------------------
    def _provider_or_raise(self) -> VisionProvider:
        provider = self._provider
        if provider is None:
            provider = get_vision_provider("ollama", model=self.config.model,
                                           timeout_s=self.config.timeout_s)
            self._provider = provider
        probe = provider.available()
        if not probe.get("available"):
            raise VisionUnavailable(str(probe.get("reason", "VISION UNAVAILABLE")))
        return provider

    def availability(self) -> Dict[str, Any]:
        try:
            provider = self._provider_or_raise()
            probe = provider.available()
        except VisionUnavailable as exc:
            with self._lock:
                self._state = "UNAVAILABLE"
                self._last_error = str(exc)[:300]
            return {"available": False, "reason": str(exc)[:300]}
        except Exception as exc:
            with self._lock:
                self._state = "UNAVAILABLE"
                self._last_error = str(exc)[:300]
            return {"available": False, "reason": str(exc)[:300]}
        with self._lock:
            self._state = "READY"
            self._last_error = ""
        return {"available": True, **{k: v for k, v in probe.items() if k != "available"}}

    # --------------------------------------------------
    # Sources (explicit only)
    # --------------------------------------------------
    def capture_screenshot(self) -> Tuple[bytes, str, int, int]:
        """Capture the screen on Windows (honest when uncapturable)."""
        try:
            from PIL import ImageGrab  # type: ignore
        except Exception:
            raise VisionUnavailable(
                "screenshot unavailable (Pillow not installed: pip install Pillow)")
        try:
            import io as _io

            image = ImageGrab.grab()
            width, height = int(image.size[0]), int(image.size[1])
            buffer = _io.BytesIO()
            image.save(buffer, format="PNG")
            data = buffer.getvalue()
        except Exception as exc:
            raise VisionUnavailable(f"screenshot capture failed: {exc}")
        self._check_bounds(data, width, height)
        return data, "image/png", width, height

    def load_image_file(self, path: str) -> Tuple[bytes, str, int, int]:
        target = workspace_image_path(path)
        if not target.exists() or not target.is_file():
            raise ValueError(f"image not found: {path}")
        data = target.read_bytes()
        width, height, mime = image_dimensions(data)
        if mime == "application/octet-stream":
            raise ValueError(f"unsupported image type: {path}")
        self._check_bounds(data, width, height)
        return data, mime, width, height

    def _check_bounds(self, data: bytes, width: int, height: int) -> None:
        if len(data) > self.config.max_bytes:
            raise ValueError(
                f"image too large ({len(data)} bytes > {self.config.max_bytes}); "
                "use a smaller image")
        if width and width > self.config.max_dim_px:
            raise ValueError(
                f"image too wide ({width}px > {self.config.max_dim_px}); "
                "use a smaller image")
        if height and height > self.config.max_dim_px:
            raise ValueError(
                f"image too tall ({height}px > {self.config.max_dim_px}); "
                "use a smaller image")

    # --------------------------------------------------
    # OCR (separated from visual reasoning)
    # --------------------------------------------------
    def extract_text(self, image: bytes) -> Dict[str, Any]:
        """OCR a PNG/JPEG byte payload when tesseract is installed."""
        if not self.config.ocr_enabled:
            return {"available": False, "reason": "OCR disabled by configuration",
                    "text": []}
        try:
            import pytesseract  # type: ignore
            from PIL import Image  # type: ignore
            import io as _io
        except Exception:
            return {"available": False,
                    "reason": "OCR unavailable (pytesseract/Pillow not installed)",
                    "text": []}
        try:
            pil_image = Image.open(_io.BytesIO(image))
            raw = pytesseract.image_to_string(pil_image) or ""
        except Exception as exc:
            return {"available": False, "reason": f"OCR failed: {exc}",
                    "text": []}
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()][:50]
        return {"available": True, "text": lines}

    # --------------------------------------------------
    # Analysis (explicit, bounded, read-only)
    # --------------------------------------------------
    def analyze_bytes(self, image: bytes, mime: str, prompt: str = "",
                      width: int = 0, height: int = 0,
                      source: str = "image-file") -> Dict[str, Any]:
        provider = self._provider_or_raise()
        if not image:
            raise ValueError("empty image: nothing to analyze")
        self._check_bounds(image, width or 0, height or 0)
        with self._lock:
            self._state = "ANALYZING"
            self._last_error = ""
        try:
            payload_b64 = base64.b64encode(image).decode("ascii")
            observation = provider.describe(payload_b64, mime,
                                            prompt or "Describe this image.",
                                            width=width, height=height,
                                            source=source)
            validated = validate_observation(observation).as_dict()
        except (VisionUnavailable, ValueError):
            with self._lock:
                self._state = "UNAVAILABLE"
            raise
        except Exception as exc:
            with self._lock:
                self._state = "UNAVAILABLE"
                self._last_error = str(exc)[:300]
            raise VisionUnavailable(f"vision analysis failed: {exc}")
        # OCR enrichment is advisory only: model text always wins, OCR
        # appends lines the model missed (never overwrites, never blocks).
        try:
            ocr = self.extract_text(image)
            if ocr.get("available") and ocr.get("text"):
                seen = set(validated.get("detected_text", []))
                for line in ocr["text"]:
                    if line not in seen:
                        validated["detected_text"].append(line)
                        seen.add(line)
                validated["ocr_available"] = True
            else:
                validated["ocr_available"] = False
        except Exception:
            validated["ocr_available"] = False
        with self._lock:
            self._state = "RESULT"
            self._last_observation = validated
        return validated

    def analyze_screenshot(self, prompt: str = "") -> Dict[str, Any]:
        data, mime, width, height = self.capture_screenshot()
        return self.analyze_bytes(data, mime, prompt=prompt or
                                  "Describe what is on this screen.",
                                  width=width, height=height,
                                  source="screenshot")

    def analyze_file(self, path: str, prompt: str = "") -> Dict[str, Any]:
        data, mime, width, height = self.load_image_file(path)
        return self.analyze_bytes(data, mime, prompt=prompt or
                                  "Describe this image.",
                                  width=width, height=height,
                                  source="image-file")

    # --------------------------------------------------
    def snapshot(self) -> Dict[str, Any]:
        """HUD state: real values only (never fabricated observations)."""
        with self._lock:
            last = dict(self._last_observation or {})
            return {
                "state": self._state,
                "ready": self._state in ("READY", "RESULT"),
                "analyzing": self._state == "ANALYZING",
                "has_result": bool(self._last_observation),
                "description": str(last.get("description", ""))[:200],
                "confidence": last.get("confidence", 0.0),
                "source": str(last.get("source", "")),
                "model": str(last.get("model", "")),
                "error": self._last_error[:200],
            }
