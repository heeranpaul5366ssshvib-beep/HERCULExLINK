from __future__ import annotations
"""
--------------------------------------------
HERCULE Automation Demo Plugin
Demonstrates sensitive automation permission
--------------------------------------------
"""

import time
from typing import Any, Dict

from plugin_sdk.plugin import Plugin
from plugin_sdk.manifest import PluginCapability


class AutomationDemoPlugin(Plugin):
    """Automation demo plugin - requires sensitive automation permission."""

    name = "HERCULE Automation Demo"
    version = "1.0.0"
    author = "HERCULE Team"
    description = "Demonstrates sensitive automation permission - requires explicit approval"
    plugin_id = "hercule.automation_demo"
    capabilities = ["automation", "clipboard"]
    permissions = ["automation", "clipboard"]
    configuration_schema = {
        "safe_mode": {"type": "bool", "default": True},
    }

    def on_discover(self) -> bool:
        self.logger.info("Automation demo plugin discovered")
        return True

    def on_validate(self, hercule_version: str) -> bool:
        self.logger.info("Validating against HERCULE {}".format(hercule_version))
        return True

    def on_install(self) -> bool:
        self.logger.info("Automation demo plugin installed")
        return True

    def on_enable(self) -> bool:
        if not self.context:
            return False

        # Register automation tool
        self.context.tools.register_tool(
            name="safe_automation",
            description="Perform safe automation action (e.g., get clipboard text)",
            handler=self._safe_automation_handler,
            capability="automation",
            permissions=["automation"],
        )

        self.context.tools.register_tool(
            name="clipboard_read",
            description="Read clipboard content",
            handler=self._clipboard_read_handler,
            capability="clipboard",
            permissions=["clipboard"],
        )

        self.logger.info("Automation demo plugin enabled")
        return True

    def on_disable(self) -> bool:
        if self.context:
            self.context.tools.unregister_tool("safe_automation")
            self.context.tools.unregister_tool("clipboard_read")
        self.logger.info("Automation demo plugin disabled")
        return True

    def on_uninstall(self) -> bool:
        self.logger.info("Automation demo plugin uninstalled")
        return True

    def on_reload(self) -> bool:
        self.logger.info("Automation demo plugin reloaded")
        return True

    def health(self) -> Dict[str, Any]:
        base = super().health()
        base.update({
            "tools_registered": 2,
            "automation_approved": self.context.permissions.has("automation") if self.context else False,
        })
        return base

    def execute(self, *args, **kwargs) -> Any:
        return {"status": "use_tools_instead"}

    def _safe_automation_handler(self, action: str = "noop") -> Dict[str, Any]:
        """Perform a safe automation action."""
        # Check automation permission
        try:
            self.context.permissions.check("automation")
        except PermissionError as e:
            return {"error": str(e), "approved": False}

        safe_mode = self.context.config.get("safe_mode", True)
        
        if action == "noop":
            return {"action": "noop", "result": "Safe automation noop executed", "approved": True}
        elif action == "get_time":
            return {"action": "get_time", "result": time.time(), "approved": True}
        else:
            if safe_mode:
                return {"error": "Action not allowed in safe mode: {}".format(action), "approved": False}
            return {"action": action, "result": "executed", "approved": True}

    def _clipboard_read_handler(self) -> Dict[str, Any]:
        """Read clipboard content (requires clipboard permission)."""
        try:
            self.context.permissions.check("clipboard")
        except PermissionError as e:
            return {"error": str(e), "approved": False}
        
        # In a real plugin, this would use pyperclip or similar
        # For demo, we just return a safe message
        return {
            "content": "[clipboard content would appear here]",
            "approved": True,
            "note": "Clipboard access simulated for demo"
        }