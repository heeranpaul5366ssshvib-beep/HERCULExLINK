from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Plugin Registry - Extended with lifecycle tracking
--------------------------------------------
"""

import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from plugin_sdk.plugin import Plugin, PluginStatus, PluginContext
from plugin_sdk.manifest import PluginManifest
from plugin_sdk.permissions import PluginPermissionModel, PluginPermissionChecker
from plugin_sdk.plugin_loader import PluginLoader


logger = logging.getLogger("HERCULE.PluginRegistry")


class PluginRegistry:
    """
    Extended plugin registry with full lifecycle management.
    """

    def __init__(
        self,
        loader: PluginLoader,
        permission_model: PluginPermissionModel,
        ability_manager: Optional[Any] = None,
        memory_manager: Optional[Any] = None,
        model_router: Optional[Any] = None,
        security_manager: Optional[Any] = None,
        event_bus: Optional[Any] = None,
        workspace_path: str = "data/plugins/workspace",
    ):
        self._loader = loader
        self._permission_model = permission_model
        self._ability_manager = ability_manager
        self._memory_manager = memory_manager
        self._model_router = model_router
        self._security_manager = security_manager
        self._event_bus = event_bus
        self._workspace_path = workspace_path

        self._plugins: Dict[str, Plugin] = {}
        self._manifests: Dict[str, PluginManifest] = {}
        self._configs: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()

        # Activity log
        self._activity_log: List[Dict[str, Any]] = []
        self._max_activity_log = 1000

    # ============================================================
    # REGISTRATION
    # ============================================================

    def register(self, plugin: Plugin) -> None:
        """Register a plugin instance."""
        with self._lock:
            plugin_id = plugin.plugin_id
            if plugin_id in self._plugins:
                raise ValueError(f"Plugin {plugin_id} already registered")
            self._plugins[plugin_id] = plugin
            if plugin.manifest:
                self._manifests[plugin_id] = plugin.manifest
            logger.info(f"Registered plugin: {plugin_id}")

    def unregister(self, plugin_id: str) -> None:
        """Unregister a plugin."""
        with self._lock:
            plugin = self._plugins.pop(plugin_id, None)
            self._manifests.pop(plugin_id, None)
            if plugin:
                logger.info(f"Unregistered plugin: {plugin_id}")

    def get(self, plugin_id: str) -> Optional[Plugin]:
        with self._lock:
            return self._plugins.get(plugin_id)

    def all(self) -> List[Plugin]:
        with self._lock:
            return list(self._plugins.values())

    def names(self) -> List[str]:
        with self._lock:
            return list(self._plugins.keys())

    def clear(self) -> None:
        with self._lock:
            self._plugins.clear()
            self._manifests.clear()
            self._configs.clear()

    # ============================================================
    # CONFIGURATION
    # ============================================================

    def get_config(self, plugin_id: str) -> Dict[str, Any]:
        with self._lock:
            return self._configs.get(plugin_id, {}).copy()

    def set_config(self, plugin_id: str, config: Dict[str, Any]) -> None:
        with self._lock:
            self._configs[plugin_id] = config.copy()
            # Update plugin instance if loaded
            plugin = self._plugins.get(plugin_id)
            if plugin:
                plugin.set_config(config)

    def save_config(self, plugin_id: str, config_dir: str = "config/plugins") -> bool:
        """Save plugin config to disk."""
        config = self._configs.get(plugin_id, {})
        config_path = Path(config_dir) / f"{plugin_id}.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            import json
            config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
            return True
        except Exception as e:
            logger.error(f"Failed to save config for {plugin_id}: {e}")
            return False

    def load_config(self, plugin_id: str, config_dir: str = "config/plugins") -> Dict[str, Any]:
        """Load plugin config from disk."""
        config_path = Path(config_dir) / f"{plugin_id}.json"
        if config_path.exists():
            try:
                import json
                config = json.loads(config_path.read_text(encoding="utf-8"))
                self._configs[plugin_id] = config
                return config
            except Exception as e:
                logger.error(f"Failed to load config for {plugin_id}: {e}")
        return {}

    # ============================================================
    # ACTIVITY LOG
    # ============================================================

    def log_activity(
        self,
        plugin_id: str,
        capability: str,
        permission: str,
        success: bool,
        duration_ms: float,
        error: Optional[str] = None,
    ) -> None:
        """Log plugin activity for audit."""
        entry = {
            "timestamp": time.time(),
            "plugin_id": plugin_id,
            "capability": capability,
            "permission": permission,
            "success": success,
            "duration_ms": duration_ms,
        }
        if error:
            entry["error"] = error
        self._activity_log.append(entry)
        if len(self._activity_log) > self._max_activity_log:
            self._activity_log = self._activity_log[-self._max_activity_log:]

    def get_activity(self, plugin_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            return [a for a in self._activity_log if a["plugin_id"] == plugin_id][-limit:]

    def get_all_activity(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            return self._activity_log[-limit:]

    # ============================================================
    # MANIFEST ACCESS
    # ============================================================

    def get_manifest(self, plugin_id: str) -> Optional[PluginManifest]:
        with self._lock:
            return self._manifests.get(plugin_id)

    def has_manifest(self, plugin_id: str) -> bool:
        with self._lock:
            return plugin_id in self._manifests