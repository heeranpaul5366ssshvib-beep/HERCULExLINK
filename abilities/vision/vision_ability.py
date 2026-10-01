from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Vision Ability (v1.1, read-only)
Author: Heeran Paul
License: MIT
--------------------------------------------

Read-only visual perception inside the existing ability pipeline
(capability -> permission -> execution -> verification). Exposes
screenshot / image-file analysis as structured observations. NEVER
clicks, types, executes, or modifies files: observation only.
"""

import re as _re

from abilities.base_ability import BaseAbility


class VisionAbility(BaseAbility):

    def __init__(self):

        super().__init__(
            "vision",
            "Analyze screenshots and workspace images into structured observations (read-only)",
            capability="VISION_ANALYSIS",
            inputs={"source": "screenshot|image-file",
                    "path": "workspace-relative image path (image-file only)",
                    "prompt": "what to describe"},
            outputs={"observation": "structured description/text/regions/confidence"},
            permissions=["VISION_ANALYSIS"],
            environments={"default"},
            verification="structured observation with description and confidence",
            timeout_s=90,
            risk="MEDIUM",
        )

    def validate_input(self, task, **kwargs):
        if isinstance(task, dict):
            source = str(task.get("source", "") or "").lower()
            if source and source not in ("screenshot", "image-file"):
                return "source must be screenshot|image-file"
            if source == "image-file" and not str(task.get("path", "") or "").strip():
                return "image-file source needs a workspace-relative path"
            return ""
        text = str(task or "")
        if not text.strip() and not kwargs.get("path"):
            return "empty vision request"
        return ""

    def execute(self, task="", context=None, **kwargs):
        source = str(kwargs.pop("source", "") or "").lower()
        path = str(kwargs.pop("path", "") or "")
        prompt = str(kwargs.pop("prompt", "") or "")
        text = task if isinstance(task, str) else ""
        if isinstance(task, dict):
            source = source or str(task.get("source", "")).lower()
            path = path or str(task.get("path", ""))
            prompt = prompt or str(task.get("prompt", task.get("description", "")))
            text = str(task.get("description", text or ""))
        if not source:
            lowered = f"{text} {path} {prompt}".lower()
            if "screenshot" in lowered or "screen" in lowered:
                source = "screenshot"
            else:
                match = _re.search(r"[\w\-./\\]+\.(png|jpe?g|bmp|gif|webp)", f"{text} {path}",
                                   _re.IGNORECASE)
                if match:
                    source = "image-file"
                    path = path or match.group(0)
                else:
                    source = "screenshot"
        if not prompt:
            prompt = text or "Describe this image."
        try:
            from perception.vision.manager import VisionManager

            manager = VisionManager()
            if source == "screenshot":
                observation = manager.analyze_screenshot(prompt)
            else:
                if not path:
                    return {"status": "failed", "source": source,
                            "error": "no image path specified"}
                observation = manager.analyze_file(path, prompt)
        except Exception as error:
            return {"status": "failed", "source": source or "unknown",
                    "error": str(error)[:300]}
        return {"status": "success", "source": observation.get("source", source),
                "observation": observation,
                "content": observation.get("description", "")}
