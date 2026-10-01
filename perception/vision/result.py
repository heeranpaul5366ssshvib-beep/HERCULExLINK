from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Structured Vision Observation (v1.1)
Author: Heeran Paul
License: MIT
--------------------------------------------

Structured vision results. Raw model output is NEVER passed to
execution: providers return free text/JSON, and only a validated
StructuredObservation reaches the Brain/planner/abilities.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class StructuredObservation:
    description: str = ""
    detected_text: List[str] = field(default_factory=list)
    regions: List[Dict[str, Any]] = field(default_factory=list)
    objects: List[str] = field(default_factory=list)
    confidence: float = 0.0
    source: str = ""  # screenshot | image-file | camera
    model: str = ""
    width: int = 0
    height: int = 0
    ocr_available: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "description": self.description,
            "detected_text": list(self.detected_text),
            "regions": [dict(r) for r in self.regions],
            "objects": list(self.objects),
            "confidence": self.confidence,
            "source": self.source,
            "model": self.model,
            "width": self.width,
            "height": self.height,
            "ocr_available": self.ocr_available,
        }


def validate_observation(data: Dict[str, Any]) -> StructuredObservation:
    """Validate a provider payload into a StructuredObservation.

    Raises ValueError on malformed output (caller reports honestly,
    never executes).
    """
    if not isinstance(data, dict):
        raise ValueError("malformed vision output: not a mapping")
    description = str(data.get("description", "") or "").strip()
    if not description:
        raise ValueError("malformed vision output: missing description")
    detected = data.get("detected_text", [])
    if detected is None:
        detected = []
    if not isinstance(detected, (list, tuple)):
        raise ValueError("malformed vision output: detected_text must be a list")
    detected_text = [str(t).strip() for t in detected if str(t or "").strip()][:50]
    regions = data.get("regions", [])
    if regions is None:
        regions = []
    if not isinstance(regions, (list, tuple)):
        raise ValueError("malformed vision output: regions must be a list")
    clean_regions: List[Dict[str, Any]] = []
    for region in list(regions)[:50]:
        if not isinstance(region, dict):
            raise ValueError("malformed vision output: region must be a mapping")
        label = str(region.get("label", "") or "")[:120]
        try:
            x = float(region.get("x", 0.0))
            y = float(region.get("y", 0.0))
            w = float(region.get("width", region.get("w", 0.0)))
            h = float(region.get("height", region.get("h", 0.0)))
            conf = float(region.get("confidence", 0.0))
        except (TypeError, ValueError):
            raise ValueError("malformed vision output: region fields must be numeric")
        for value in (x, y, w, h):
            if not (0.0 <= value <= 1.0):
                raise ValueError("malformed vision output: region box must be 0..1 relative")
        if not (0.0 <= conf <= 1.0):
            raise ValueError("malformed vision output: region confidence must be 0..1")
        clean_regions.append({"label": label, "x": x, "y": y,
                              "width": w, "height": h, "confidence": conf})
    objects = data.get("objects", [])
    if objects is None:
        objects = []
    if not isinstance(objects, (list, tuple)):
        raise ValueError("malformed vision output: objects must be a list")
    clean_objects = [str(o).strip()[:120] for o in objects if str(o or "").strip()][:50]
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        raise ValueError("malformed vision output: confidence must be numeric")
    if not (0.0 <= confidence <= 1.0):
        raise ValueError("malformed vision output: confidence must be 0..1")
    source = str(data.get("source", "") or "")[:32]
    if source not in ("screenshot", "image-file", "camera"):
        raise ValueError("malformed vision output: unknown source")
    try:
        width = int(data.get("width", 0) or 0)
        height = int(data.get("height", 0) or 0)
    except (TypeError, ValueError):
        raise ValueError("malformed vision output: dimensions must be integers")
    if width < 0 or height < 0:
        raise ValueError("malformed vision output: negative dimensions")
    return StructuredObservation(
        description=description[:2000],
        detected_text=detected_text,
        regions=clean_regions,
        objects=clean_objects,
        confidence=confidence,
        source=source,
        model=str(data.get("model", "") or "")[:120],
        width=width,
        height=height,
        ocr_available=bool(data.get("ocr_available", False)),
    )
