from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Plugin Base Class
--------------------------------------------
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import logging
import os

from plugin_sdk.manifest import PluginManifest, PluginPermission, PluginCapability, PluginStatus
from plugin_sdk.model_access import PluginModelAccess
from plugin_sdk.events import PluginEventType


class PluginContext:
    """
    Controlled context object provided to plugins.
    Every operation passes through the relevant policy layer.
    Plugins should not directly manipulate Brain internals.
    """

    def __init__(
        self,
        plugin_id: str,
        logger: logging.Logger,
        config: Dict[str, Any],
        events: "PluginEventBus",
        tools: "PluginToolRegistry",
        memory: "PluginMemoryAccess",
        permissions: "PluginPermissionChecker",
        workspace: "PluginWorkspaceAccess",
        ui_hooks: "PluginUIHooks",
        model_access: Optional["PluginModelAccess"] = None,
    ):
        self._plugin_id = plugin_id
        self._logger = logger
        self._config = config
        self._events = events
        self._tools = tools
        self._memory = memory
        self._permissions = permissions
        self._workspace = workspace
        self._ui_hooks = ui_hooks
        self._model_access = model_access

    @property
    def plugin_id(self) -> str:
        return self._plugin_id

    @property
    def logger(self) -> logging.Logger:
        return self._logger

    @property
    def config(self) -> Dict[str, Any]:
        return self._config.copy()

    def set_config(self, key: str, value: Any) -> None:
        self._config[key] = value

    @property
    def events(self) -> "PluginEventBus":
        return self._events

    @property
    def tools(self) -> "PluginToolRegistry":
        return self._tools

    @property
    def memory(self) -> "PluginMemoryAccess":
        return self._memory

    @property
    def permissions(self) -> "PluginPermissionChecker":
        return self._permissions

    @property
    def workspace(self) -> "PluginWorkspaceAccess":
        return self._workspace

    @property
    def ui_hooks(self) -> "PluginUIHooks":
        return self._ui_hooks

    @property
    def model_access(self) -> Optional["PluginModelAccess"]:
        return self._model_access


class PluginEventBus:
    """Controlled event system for plugins."""

    # Events that plugins are allowed to subscribe to
    ALLOWED_SUBSCRIPTIONS: set = {
        PluginEventType.ON_STARTUP,
        PluginEventType.ON_SHUTDOWN,
        PluginEventType.ON_TASK_CREATED,
        PluginEventType.ON_TASK_COMPLETED,
        PluginEventType.ON_TASK_FAILED,
        PluginEventType.ON_TOOL_RESULT,
        PluginEventType.ON_MEMORY_UPDATE,
        PluginEventType.ON_PROJECT_OPEN,
        PluginEventType.ON_PROJECT_CLOSE,
    }

    # Events that plugins can emit
    ALLOWED_EMISSIONS: set = {
        PluginEventType.ON_PLUGIN_ENABLED,
        PluginEventType.ON_PLUGIN_DISABLED,
    }

    def __init__(self, plugin_id: str, core_event_bus: Optional[Any] = None):
        self._plugin_id = plugin_id
        self._core_bus = core_event_bus
        self._handlers: Dict[str, List[callable]] = {}

    def subscribe(self, event_name: str, handler: callable) -> bool:
        """Subscribe to an event. Only allowed events can be subscribed."""
        if event_name not in self.ALLOWED_SUBSCRIPTIONS:
            import logging
            logger = logging.getLogger(f"HERCULE.Plugin.{self._plugin_id}")
            logger.warning(f"Plugin {self._plugin_id} attempted to subscribe to disallowed event: {event_name}")
            return False
        
        if event_name not in self._handlers:
            self._handlers[event_name] = []
        self._handlers[event_name].append(handler)
        return True

    def unsubscribe(self, event_name: str, handler: callable) -> bool:
        """Unsubscribe from an event."""
        if event_name in self._handlers:
            try:
                self._handlers[event_name].remove(handler)
                return True
            except ValueError:
                pass
        return False

    def emit(self, event_name: str, data: Any = None) -> None:
        # Local handlers
        for handler in self._handlers.get(event_name, []):
            try:
                handler(data)
            except Exception:
                pass  # Don't let plugin handlers crash the system
        # Forward to core event bus if available
        if self._core_bus and hasattr(self._core_bus, "publish"):
            try:
                self._core_bus.publish(f"plugin.{self._plugin_id}.{event_name}", data)
            except Exception:
                pass


class PluginToolRegistry:
    """Tool/ability registration for plugins."""

    def __init__(self, plugin_id: str, ability_manager: Optional[Any] = None):
        self._plugin_id = plugin_id
        self._ability_manager = ability_manager
        self._registered_tools: Dict[str, Any] = {}

    def register_tool(
        self,
        name: str,
        description: str,
        handler: callable,
        permissions: Optional[List[str]] = None,
        capability: Optional[str] = None,
    ) -> None:
        """Register a tool that goes through normal HERCULE routing."""
        if self._ability_manager:
            # Create a dynamic ability for this tool
            from abilities.base_ability import BaseAbility
            plugin_id = self._plugin_id

            class PluginToolAbility(BaseAbility):
                def __init__(self):
                    super().__init__(
                        name=f"{plugin_id}.{name}",
                        description=description,
                        capability=capability or name,
                        permissions=permissions or [capability or name],
                        risk="LOW",
                    )

                def execute(self, *args, **kwargs):
                    return handler(*args, **kwargs)

                def validate_input(self, *args, **kwargs):
                    return None

            ability = PluginToolAbility()
            self._ability_manager.register(ability)
            self._registered_tools[name] = ability

    def unregister_tool(self, name: str) -> None:
        full_name = f"{self._plugin_id}.{name}"
        if full_name in self._registered_tools:
            self._ability_manager.unregister(full_name)
            del self._registered_tools[name]


class PluginMemoryAccess:
    """Scoped memory access for plugins."""

    def __init__(self, plugin_id: str, memory_manager: Optional[Any] = None):
        self._plugin_id = plugin_id
        self._memory = memory_manager

    def store(self, key: str, value: Any) -> bool:
        if not self._memory:
            return False
        try:
            scoped_key = f"plugin.{self._plugin_id}.{key}"
            self._memory.store(scoped_key, value)
            return True
        except Exception:
            return False

    def retrieve(self, key: str) -> Any:
        if not self._memory:
            return None
        try:
            scoped_key = f"plugin.{self._plugin_id}.{key}"
            return self._memory.retrieve(scoped_key)
        except Exception:
            return None

    def search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        if not self._memory:
            return []
        try:
            return self._memory.search_memory(query, limit=limit)
        except Exception:
            return []


class PluginPermissionChecker:
    """Permission checking for plugins."""

    def __init__(self, plugin_id: str, granted_permissions: List[str], security_manager: Optional[Any] = None):
        self._plugin_id = plugin_id
        self._granted = set(granted_permissions)
        self._security = security_manager

    def has(self, permission: str) -> bool:
        return permission in self._granted

    def check(self, permission: str) -> bool:
        if permission not in self._granted:
            raise PermissionError(f"Plugin '{self._plugin_id}' does not have permission: {permission}")
        return True

    def request(self, permission: str) -> bool:
        """Request a new permission (requires user approval)."""
        # This would trigger an approval flow
        return False


class PluginWorkspaceAccess:
    """Restricted workspace access for plugins."""

    def __init__(self, plugin_id: str, base_path: str, permissions: PluginPermissionChecker):
        self._plugin_id = plugin_id
        self._base_path = os.path.abspath(base_path)
        self._permissions = permissions

    def _resolve_path(self, path: str) -> str:
        """Resolve path and ensure it's within the base workspace."""
        # Resolve the full path
        full_path = os.path.abspath(os.path.join(self._base_path, path))
        # Ensure it's within the base path (prevent directory traversal)
        if not full_path.startswith(self._base_path):
            raise PermissionError("Path traversal attempt blocked: {}".format(path))
        return full_path

    def read_file(self, path: str) -> Optional[str]:
        self._permissions.check(PluginPermission.FILESYSTEM_READ.value)
        try:
            full_path = self._resolve_path(path)
        except PermissionError:
            return None
        if not os.path.exists(full_path):
            return None
        with open(full_path, "r", encoding="utf-8") as f:
            return f.read()

    def write_file(self, path: str, content: str) -> bool:
        self._permissions.check(PluginPermission.FILESYSTEM_WRITE.value)
        try:
            full_path = self._resolve_path(path)
        except PermissionError:
            return False
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        return True

    def list_files(self, path: str = "") -> List[str]:
        self._permissions.check(PluginPermission.FILESYSTEM_READ.value)
        try:
            full_path = self._resolve_path(path)
        except PermissionError:
            return []
        if not os.path.exists(full_path):
            return []
        return os.listdir(full_path)


class PluginUIHooks:
    """UI integration hooks for plugins."""

    def __init__(self, plugin_id: str):
        self._plugin_id = plugin_id
        self._panels: Dict[str, Dict[str, Any]] = {}

    def register_panel(self, panel_id: str, title: str, component: str, position: str = "sidebar") -> None:
        self._panels[panel_id] = {
            "title": title,
            "component": component,
            "position": position,
        }

    def unregister_panel(self, panel_id: str) -> None:
        self._panels.pop(panel_id, None)

    def get_panels(self) -> Dict[str, Dict[str, Any]]:
        return self._panels.copy()


class Plugin(ABC):
    """
    Base class for every HERCULE plugin.
    Provides full lifecycle, manifest, permissions, and controlled context.
    """

    # Class-level metadata (can be overridden by manifest)
    name = "Unnamed Plugin"
    version = "1.0.0"
    author = "Unknown"
    description = ""
    plugin_id = ""
    capabilities: List[str] = []
    permissions: List[str] = []
    dependencies: List[str] = []
    configuration_schema: Dict[str, Any] = {}
    min_hercule_version = "1.0.0"
    max_hercule_version: Optional[str] = None
    plugin_api_version = "1.0"

    def __init__(self):
        self._manifest: Optional[PluginManifest] = None
        self._context: Optional[PluginContext] = None
        self._status = PluginStatus.DISCOVERED
        self._config: Dict[str, Any] = {}
        self._last_error: Optional[str] = None
        self._enabled = False

    @property
    def manifest(self) -> Optional[PluginManifest]:
        return self._manifest

    @property
    def context(self) -> Optional[PluginContext]:
        return self._context

    @property
    def status(self) -> PluginStatus:
        return self._status

    @property
    def config(self) -> Dict[str, Any]:
        return self._config.copy()

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def logger(self) -> logging.Logger:
        """Get a logger for this plugin. Uses context logger if available, otherwise creates one."""
        if self._context and self._context.logger:
            return self._context.logger
        return logging.getLogger(f"HERCULE.Plugin.{self.plugin_id or self.__class__.__name__}")

    def set_manifest(self, manifest: PluginManifest) -> None:
        self._manifest = manifest
        # Update instance attributes from manifest
        self.plugin_id = manifest.plugin_id
        self.name = manifest.name
        self.version = manifest.version
        self.author = manifest.author
        self.description = manifest.description
        self.capabilities = manifest.capabilities
        self.permissions = manifest.permissions
        self.dependencies = manifest.dependencies
        self.configuration_schema = manifest.configuration_schema
        self.min_hercule_version = manifest.min_hercule_version
        self.max_hercule_version = manifest.max_hercule_version
        self.plugin_api_version = manifest.plugin_api_version

    def set_context(self, context: PluginContext) -> None:
        self._context = context

    def set_config(self, config: Dict[str, Any]) -> None:
        self._config = config.copy()

    def _set_status(self, status: PluginStatus) -> None:
        self._status = status
        if self._context and self._context.logger:
            self._context.logger.info(f"Plugin {self.plugin_id} status: {status.value}")

    def _set_error(self, error: str) -> None:
        self._last_error = error
        if self._context and self._context.logger:
            self._context.logger.error(f"Plugin {self.plugin_id} error: {error}")

    # ============================================================
    # LIFECYCLE METHODS - Override in subclasses
    # ============================================================

    def on_discover(self) -> bool:
        """Called when plugin is discovered. Return True if valid."""
        return True

    def on_validate(self, hercule_version: str) -> bool:
        """Validate plugin compatibility. Return True if compatible."""
        return True

    def on_install(self) -> bool:
        """Called during installation. Return True on success."""
        return True

    def on_enable(self) -> bool:
        """Called when plugin is enabled. Return True on success."""
        self._enabled = True
        self._set_status(PluginStatus.ENABLED)
        return True

    def on_disable(self) -> bool:
        """Called when plugin is disabled. Return True on success."""
        self._enabled = False
        self._set_status(PluginStatus.DISABLED)
        return True

    def on_uninstall(self) -> bool:
        """Called during uninstallation. Return True on success."""
        return True

    def on_reload(self) -> bool:
        """Called when plugin is reloaded. Return True on success."""
        return True

    def on_startup(self) -> None:
        """Called on HERCULE startup if plugin is enabled."""
        pass

    def on_shutdown(self) -> None:
        """Called on HERCULE shutdown."""
        pass

    def health(self) -> Dict[str, Any]:
        """Return plugin health information."""
        return {
            "status": self._status.value,
            "version": self.version,
            "enabled": self._enabled,
            "permissions": self.permissions,
            "capabilities": self.capabilities,
            "last_error": self._last_error,
        }

    # ============================================================
    # EXECUTION - Abstract method for backward compatibility
    # ============================================================

    @abstractmethod
    def execute(self, *args, **kwargs):
        pass

    # ============================================================
    # INFO
    # ============================================================

    def info(self) -> Dict[str, Any]:
        return {
            "plugin_id": self.plugin_id,
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "capabilities": self.capabilities,
            "permissions": self.permissions,
            "status": self._status.value,
            "enabled": self._enabled,
        }