from __future__ import annotations
"""Multimodal datasets — capability-gated (Phase 2).

HERCULE ships a vision capability only when ModelManager reports a
vision-capable model installed (``vision`` capability from the Ollama
server) AND a vision adapter is configured. When the capability is
absent the suite loader returns an empty list and the runner reports
the suite as skipped — an honest absence, never a fabricated score.
"""

import importlib
from typing import Any, Dict, List

from evaluation.framework.task import EvalCategory, EvalTask, SafetyClass, ScoringMethod


def vision_capability_available(services: Any = None) -> bool:
    """True only when an actual, usable vision capability is present.

    Requires BOTH:
      1. a registered VISION capability backed by a real ability, and
      2. a vision-capable model actually installed/registered
         (server-reported ``vision`` capability).

    An importable perception module alone is NOT sufficient — module
    existence never counts as capability. Never returns True by default.
    """
    has_ability = False
    try:  # 1) capability registry + ability binding
        from cognition.capabilities.registry import CapabilityRegistry
        from abilities.ability_manager import AbilityManager
        abilities = getattr(services, "get", lambda _k: None)("abilities") if services else None
        if abilities is None:
            abilities = AbilityManager()
        registry = CapabilityRegistry()
        registry.register_default_tools(abilities)
        has_ability = "VISION" in (registry.capabilities() or [])
    except Exception:
        has_ability = False
    if not has_ability:
        return False
    try:  # 2) vision-capable model installed (server-reported)
        manager = getattr(services, "get", lambda _k: None)("models") if services else None
        if manager is not None:
            registry_obj = getattr(getattr(manager, "router", None), "registry", None)
            for info in (registry_obj.list_all() if registry_obj else []) or []:
                if "vision" in [str(c).lower() for c in getattr(info, "capabilities", [])]:
                    return True
    except Exception:
        pass
    return False


def multimodal_tasks(services: Any = None) -> List[EvalTask]:
    """One vision-style task when (and only when) vision exists."""
    if not vision_capability_available(services):
        return []
    return [
        EvalTask(
            task_id="multimodal-vision-001",
            suite="multimodal",
            category=EvalCategory.MULTIMODAL,
            prompt=("Vision probe: an image containing the word HERCULE is provided "
                    "to the vision capability. Transcribe the word you see."),
            expected_format="transcribed word",
            scoring_method=ScoringMethod.EXACT_MATCH,
            expected=["hercule"],
            evaluator="exact transcription match",
            difficulty="medium", timeout_s=120.0,
            safety_class=SafetyClass.READ_ONLY, style="multimodal OCR-style",
        ),
    ]
