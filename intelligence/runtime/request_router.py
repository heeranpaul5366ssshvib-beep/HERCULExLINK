from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Request Router
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


import logging
from enum import Enum
from typing import Any, Dict


logger = logging.getLogger(__name__)


class RequestType(Enum):

    CHAT = "chat"

    COMMAND = "command"

    AUTOMATION = "automation"

    RESEARCH = "research"

    CODING = "coding"

    ENGINEERING = "engineering"

    ROBOTICS = "robotics"

    UNKNOWN = "unknown"


class RequestRouter:
    """
    Determines which subsystem should receive a request.

    Architecture: deterministic capability inference (cognition) is the
    primary signal — a request bearing required capabilities is a TASK.
    Keyword intent patterns are a secondary signal for command families
    (coding/research/robotics/engineering/automation). Pure conversation
    (greeting/identity/general question with no capabilities) routes to
    the Brain conversation path. Nothing here executes; callers decide
    QUESTION vs GOAL from classify_detailed().
    """

    def __init__(self, kernel):

        self.kernel = kernel

        self.initialized = False

    # --------------------------------------------------

    def initialize(self):

        logger.info("Initializing Request Router")

        self.initialized = True

    # --------------------------------------------------

    def shutdown(self):

        logger.info("Stopping Request Router")

        self.initialized = False

    # --------------------------------------------------

    def route(
        self,
        request: Any,
    ) -> Dict[str, Any]:

        request_type = self.classify(request)

        destination = self.destination(
            request_type
        )

        return {

            "request": request,

            "type": request_type.value,

            "destination": destination,

        }

    # --------------------------------------------------

    def classify(
        self,
        request: Any,
    ) -> RequestType:

        return self.classify_detailed(request).get("type", RequestType.UNKNOWN)

    def classify_detailed(self, request: Any) -> Dict[str, Any]:
        """Rich classification: type + capabilities + confidence + reason.

        Uses cognition.capabilities.inference (deterministic, testable) as
        the primary signal; intent keywords only select the task family.
        Never executes. Never exposes chain-of-thought.
        """
        if not isinstance(request, str) or not request.strip():
            return {"type": RequestType.UNKNOWN, "capabilities": [],
                    "confidence": 0.0, "reason": "non-text-or-empty",
                    "destination": self.destination(RequestType.UNKNOWN)}
        text = request.strip()
        lowered = text.lower()

        capabilities: list[str] = []
        try:
            from cognition.capabilities.inference import infer_capabilities
            capabilities = [c.value for c in infer_capabilities(text)]
        except Exception as exc:
            logger.warning("capability inference failed: %s", exc)
            capabilities = []

        request_type = self._intent_family(lowered, bool(capabilities))
        confidence = 0.95 if capabilities else (0.85 if request_type != RequestType.CHAT else 0.7)
        reason = (
            f"capabilities={capabilities}" if capabilities
            else f"intent-family={request_type.value}"
        )
        logger.info("CLASSIFICATION route=%s confidence=%.2f reason=[%s] input=[%.60s]",
                    request_type.value, confidence, reason, text)
        return {"type": request_type, "capabilities": capabilities,
                "confidence": confidence, "reason": reason,
                "destination": self.destination(request_type)}

    @staticmethod
    def _intent_family(lowered: str, has_capabilities: bool) -> RequestType:
        if any(k in lowered for k in ("robot", "navigate", "localiz", "actuator")):
            return RequestType.ROBOTICS
        if any(k in lowered for k in ("engineer", "aerodynamic", "cad ", "cad", "circuit", "mechanic")):
            return RequestType.ENGINEERING
        if any(k in lowered for k in ("code", "refactor", "debug the code", "implement the function",
                                      "patch the", "write code", "fix the bug")):
            return RequestType.CODING
        if any(k in lowered for k in ("research", "literature", "survey the field")):
            return RequestType.RESEARCH
        if any(k in lowered for k in ("automate", "automation", "schedule", "workflow")):
            return RequestType.AUTOMATION
        if lowered.startswith("/") or any(k in lowered for k in ("run the", "execute the", "run tests",
                                                                 "run python", "terminal", "shell")):
            return RequestType.COMMAND
        if has_capabilities:
            # Capability-bearing but no specific family -> generic command.
            return RequestType.COMMAND
        return RequestType.CHAT

    # --------------------------------------------------

    def destination(
        self,
        request_type: RequestType,
    ) -> str:

        mapping = {

            RequestType.CHAT: "brain",

            RequestType.COMMAND: "orchestrator",

            RequestType.CODING: "coding",

            RequestType.RESEARCH: "research",

            RequestType.AUTOMATION: "automation",

            RequestType.ROBOTICS: "robotics",

            RequestType.ENGINEERING: "engineering",

            RequestType.UNKNOWN: "brain",

        }

        return mapping.get(
            request_type,
            "brain",
        )

    # --------------------------------------------------

    def statistics(self):

        return {

            "initialized": self.initialized,

            "supported_routes": len(RequestType),

        }