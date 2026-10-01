from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Plugin Event System
--------------------------------------------
"""

import logging
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum
import time
import threading


logger = logging.getLogger("HERCULE.PluginEvents")


class PluginEventType(str, Enum):
    """Standard plugin event types."""
    ON_STARTUP = "on_startup"
    ON_SHUTDOWN = "on_shutdown"
    ON_TASK_CREATED = "on_task_created"
    ON_TASK_COMPLETED = "on_task_completed"
    ON_TASK_FAILED = "on_task_failed"
    ON_TOOL_RESULT = "on_tool_result"
    ON_MEMORY_UPDATE = "on_memory_update"
    ON_PROJECT_OPEN = "on_project_open"
    ON_PROJECT_CLOSE = "on_project_close"
    ON_PLUGIN_ENABLED = "on_plugin_enabled"
    ON_PLUGIN_DISABLED = "on_plugin_disabled"


@dataclass
class PluginEvent:
    """Plugin event with metadata."""
    event_type: str
    plugin_id: str
    data: Any
    timestamp: float = field(default_factory=time.time)
    correlation_id: Optional[str] = None


class PluginEventBus:
    """
    Event bus for plugin-to-core and plugin-to-plugin communication.
    Controlled - plugins can only subscribe to allowed events.
    """

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
        self._core_bus = core_bus
        self._handlers: Dict[str, List[Callable]] = {}
        self._lock = threading.RLock()

    def subscribe(self, event_name: str, handler: Callable) -> bool:
        """Subscribe to an event. Only allowed events can be subscribed."""
        if event_name not in self.ALLOWED_SUBSCRIPTIONS:
            logger.warning(f"Plugin {self._plugin_id} attempted to subscribe to disallowed event: {event_name}")
            return False
        
        with self._lock:
            if event_name not in self._handlers:
                self._handlers[event_name] = []
            self._handlers[event_name].append(handler)
        return True

    def unsubscribe(self, event_name: str, handler: Callable) -> bool:
        """Unsubscribe from an event."""
        with self._lock:
            if event_name in self._handlers:
                try:
                    self._handlers[event_name].remove(handler)
                    return True
                except ValueError:
                    pass
        return False

    def emit(self, event_name: str, data: Any = None, correlation_id: Optional[str] = None) -> None:
        """Emit an event to core bus. Only allowed emissions."""
        if event_name not in self.ALLOWED_EMISSIONS:
            logger.warning(f"Plugin {self._plugin_id} attempted to emit disallowed event: {event_name}")
            return

        event = PluginEvent(
            event_type=event_name,
            plugin_id=self._plugin_id,
            data=data,
            correlation_id=correlation_id,
        )

        # Forward to core event bus
        if self._core_bus and hasattr(self._core_bus, "publish"):
            try:
                self._core_bus.publish(f"plugin.{self._plugin_id}.{event_name}", event)
            except Exception as e:
                logger.error(f"Failed to forward plugin event to core: {e}")

    def _dispatch_local(self, event_name: str, data: Any) -> None:
        """Dispatch event to local handlers (used by core to notify plugins)."""
        with self._lock:
            handlers = self._handlers.get(event_name, []).copy()
        
        for handler in handlers:
            try:
                handler(data)
            except Exception as e:
                logger.error(f"Plugin {self._plugin_id} handler error for {event_name}: {e}")


class CorePluginEventBus:
    """
    Core event bus that manages plugin event subscriptions and dispatches
    events from the core system to plugins.
    """

    def __init__(self, plugin_manager: Any):
        self._plugin_manager = plugin_manager
        self._lock = threading.RLock()

    def publish_core_event(self, event_type: PluginEventType, data: Any) -> None:
        """Publish a core event to all enabled plugins that subscribe to it."""
        plugins = self._plugin_manager.registry.all()
        for plugin in plugins:
            if plugin.status.value == "running" and plugin.context:
                plugin.context.events._dispatch_local(event_type.value, data)

    def publish_to_plugin(self, plugin_id: str, event_type: PluginEventType, data: Any) -> bool:
        """Publish an event to a specific plugin."""
        plugin = self._plugin_manager.registry.get(plugin_id)
        if plugin and plugin.context:
            plugin.context.events._dispatch_local(event_type.value, data)
            return True
        return False

    # Convenience methods for core events
    def on_task_created(self, task_data: Dict[str, Any]) -> None:
        self.publish_core_event(PluginEventType.ON_TASK_CREATED, task_data)

    def on_task_completed(self, task_data: Dict[str, Any]) -> None:
        self.publish_core_event(PluginEventType.ON_TASK_COMPLETED, task_data)

    def on_task_failed(self, task_data: Dict[str, Any]) -> None:
        self.publish_core_event(PluginEventType.ON_TASK_FAILED, task_data)

    def on_tool_result(self, tool_data: Dict[str, Any]) -> None:
        self.publish_core_event(PluginEventType.ON_TOOL_RESULT, tool_data)

    def on_memory_update(self, memory_data: Dict[str, Any]) -> None:
        self.publish_core_event(PluginEventType.ON_MEMORY_UPDATE, memory_data)

    def on_project_open(self, project_data: Dict[str, Any]) -> None:
        self.publish_core_event(PluginEventType.ON_PROJECT_OPEN, project_data)

    def on_project_close(self, project_data: Dict[str, Any]) -> None:
        self.publish_core_event(PluginEventType.ON_PROJECT_CLOSE, project_data)

    def on_startup(self) -> None:
        self.publish_core_event(PluginEventType.ON_STARTUP, {})

    def on_shutdown(self) -> None:
        self.publish_core_event(PluginEventType.ON_SHUTDOWN, {})