from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Plugin Model Access via ModelRouter
--------------------------------------------
"""

import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from plugin_sdk.permissions import PluginPermissionChecker
from plugin_sdk.manifest import PluginPermission


logger = logging.getLogger("HERCULE.PluginModelAccess")


@dataclass
class ModelRequest:
    """Request for model assistance."""
    task: str
    preferred_model: Optional[str] = None
    preferred_adapter: Optional[str] = None
    purpose: str = "general"  # general, reasoning, planning, coding, light, complex
    context: Optional[Dict[str, Any]] = None


@dataclass
class ModelResponse:
    """Response from model."""
    content: str
    model_name: str
    adapter_name: str
    success: bool
    error: Optional[str] = None


class PluginModelAccess:
    """
    Controlled model access for plugins via ModelRouter.
    Plugins cannot bypass HERCULE's routing/security system.
    """

    def __init__(
        self,
        plugin_id: str,
        model_router: Any,
        permission_checker: PluginPermissionChecker,
    ):
        self._plugin_id = plugin_id
        self._router = model_router
        self._permissions = permission_checker

    def request(
        self,
        task: str,
        preferred_model: Optional[str] = None,
        preferred_adapter: Optional[str] = None,
        purpose: str = "general",
        context: Optional[Dict[str, Any]] = None,
    ) -> ModelResponse:
        """
        Request model assistance through HERCULE's ModelRouter.
        All requests go through normal routing and security checks.
        """
        # Check NETWORK permission (required for model access)
        try:
            self._permissions.check(PluginPermission.NETWORK.value)
        except PermissionError:
            return ModelResponse(
                content="",
                model_name="",
                adapter_name="",
                success=False,
                error=f"Plugin {self._plugin_id} lacks NETWORK permission for model access",
            )

        if not self._router:
            return ModelResponse(
                content="",
                model_name="",
                adapter_name="",
                success=False,
                error="ModelRouter not available",
            )

        try:
            # Route through ModelRouter
            if hasattr(self._router, "route_for_purpose"):
                # New purpose-aware routing
                model_name, adapter_name, adapter = self._router.route_for_purpose(
                    purpose=purpose,
                    default_model=preferred_model or "llama3",
                    preferred_model=preferred_model,
                )
            elif hasattr(self._router, "route"):
                # Legacy routing
                adapter_name, adapter = self._router.route(
                    task=task,
                    preferred_adapter=preferred_adapter,
                    preferred_model=preferred_model,
                )
                model_name = preferred_model or "unknown"
            else:
                return ModelResponse(
                    content="",
                    model_name="",
                    adapter_name="",
                    success=False,
                    error="ModelRouter does not support required routing methods",
                )

            # Execute request
            if hasattr(adapter, "complete"):
                result = adapter.complete(task, context=context or {})
            elif hasattr(adapter, "generate"):
                result = adapter.generate(task, context=context or {})
            else:
                return ModelResponse(
                    content="",
                    model_name=model_name,
                    adapter_name=adapter_name,
                    success=False,
                    error="Adapter does not support completion",
                )

            return ModelResponse(
                content=str(result),
                model_name=model_name,
                adapter_name=adapter_name,
                success=True,
            )

        except Exception as e:
            logger.error(f"Plugin {self._plugin_id} model request failed: {e}")
            return ModelResponse(
                content="",
                model_name="",
                adapter_name="",
                success=False,
                error=str(e),
            )

    def list_available_models(self) -> List[Dict[str, Any]]:
        """List available models (read-only, requires NETWORK)."""
        try:
            self._permissions.check(PluginPermission.NETWORK.value)
        except PermissionError:
            return []

        if not self._router:
            return []

        models = []
        try:
            if hasattr(self._router, "installed_ollama_models"):
                for model in self._router.installed_ollama_models():
                    models.append({"name": model, "provider": "ollama"})
            if hasattr(self._router, "installed_hercule_lm_models"):
                for model in self._router.installed_hercule_lm_models():
                    models.append({"name": model, "provider": "hercule-lm"})
        except Exception:
            pass
        return models

    def get_router_health(self) -> Dict[str, Any]:
        """Get ModelRouter health status."""
        if not self._router or not hasattr(self._router, "health"):
            return {"status": "unavailable"}
        try:
            return self._router.health()
        except Exception:
            return {"status": "error"}