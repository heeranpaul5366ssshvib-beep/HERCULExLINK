from __future__ import annotations
"""
--------------------------------------------
HERCULE Utility Plugin
Safe utility plugin: calculator, system info, time/date
--------------------------------------------
"""

import platform
import time
import datetime
import math
from typing import Any, Dict, List

from plugin_sdk.plugin import Plugin
from plugin_sdk.manifest import PluginCapability


class UtilityPlugin(Plugin):
    """Safe utility plugin with no sensitive permissions."""

    # Class metadata (also in manifest)
    name = "HERCULE Utility"
    version = "1.0.0"
    author = "HERCULE Team"
    description = "Safe utility plugin providing calculator, system information, and time/date functions"
    plugin_id = "hercule.utility"
    capabilities = ["calculator", "system_info", "time_utility"]
    permissions = ["system_info"]
    configuration_schema = {
        "default_precision": {"type": "int", "default": 10, "minimum": 1, "maximum": 50},
        "time_format": {"type": "string", "default": "%Y-%m-%d %H:%M:%S"},
    }

    def on_discover(self) -> bool:
        """Validate environment - no special requirements."""
        self.logger.info("Utility plugin discovered")
        return True

    def on_validate(self, hercule_version: str) -> bool:
        """Validate compatibility."""
        self.logger.info(f"Validating against HERCULE {hercule_version}")
        return True

    def on_install(self) -> bool:
        """Installation - no special setup needed."""
        self.logger.info("Utility plugin installed")
        return True

    def on_enable(self) -> bool:
        """Enable - register tools."""
        if not self.context:
            self.logger.error("No context available during enable")
            return False

        # Register calculator tool
        self.context.tools.register_tool(
            name="calculate",
            description="Evaluate a mathematical expression safely",
            handler=self._calculate_handler,
            capability="calculator",
            permissions=["system_info"],  # Uses system_info for math constants
        )

        # Register system info tool
        self.context.tools.register_tool(
            name="system_info",
            description="Get system information (OS, Python, CPU, memory)",
            handler=self._system_info_handler,
            capability="system_info",
            permissions=["system_info"],
        )

        # Register time utility tool
        self.context.tools.register_tool(
            name="time_util",
            description="Get current time, format timestamps, calculate durations",
            handler=self._time_util_handler,
            capability="time_utility",
            permissions=["system_info"],
        )

        # Subscribe to startup/shutdown events
        self.context.events.subscribe("on_startup", self._on_startup)
        self.context.events.subscribe("on_shutdown", self._on_shutdown)

        self.logger.info("Utility plugin enabled - tools registered")
        return True

    def on_disable(self) -> bool:
        """Disable - unregister tools."""
        if self.context:
            self.context.tools.unregister_tool("calculate")
            self.context.tools.unregister_tool("system_info")
            self.context.tools.unregister_tool("time_util")
        self.logger.info("Utility plugin disabled")
        return True

    def on_uninstall(self) -> bool:
        """Uninstall - cleanup."""
        self.logger.info("Utility plugin uninstalled")
        return True

    def on_reload(self) -> bool:
        """Reload - re-initialize."""
        self.logger.info("Utility plugin reloaded")
        return True

    def on_startup(self) -> None:
        """HERCULE startup."""
        self.logger.info("Utility plugin: HERCULE startup")

    def on_shutdown(self) -> None:
        """HERCULE shutdown."""
        self.logger.info("Utility plugin: HERCULE shutdown")

    def _on_startup(self, data: Any) -> None:
        """Handle on_startup event."""
        self.logger.debug("Received on_startup event")

    def _on_shutdown(self, data: Any) -> None:
        """Handle on_shutdown event."""
        self.logger.debug("Received on_shutdown event")

    def health(self) -> Dict[str, Any]:
        """Health check."""
        base = super().health()
        base.update({
            "tools_registered": 3,
            "event_subscriptions": 2,
        })
        return base

    # Legacy execute method (not used with tool registration)
    def execute(self, *args, **kwargs) -> Any:
        return {"status": "use_tools_instead"}

    # ============================================================
    # Tool Handlers
    # ============================================================

    def _calculate_handler(self, expression: str, precision: int = None) -> Dict[str, Any]:
        """
        Safely evaluate a mathematical expression.
        
        Args:
            expression: Mathematical expression (e.g., "2 + 3 * 4", "sqrt(16)")
            precision: Decimal precision (uses config default if not provided)
        """
        if precision is None:
            precision = self.context.config.get("default_precision", 10)

        # Safe evaluation environment
        safe_dict = {
            "__builtins__": {},
            "abs": abs,
            "round": round,
            "min": min,
            "max": max,
            "sum": sum,
            "pow": pow,
            # Math functions
            "sqrt": math.sqrt,
            "sin": math.sin,
            "cos": math.cos,
            "tan": math.tan,
            "asin": math.asin,
            "acos": math.acos,
            "atan": math.atan,
            "log": math.log,
            "log10": math.log10,
            "exp": math.exp,
            "pi": math.pi,
            "e": math.e,
            "ceil": math.ceil,
            "floor": math.floor,
        }

        try:
            # Validate expression only contains safe characters
            allowed_chars = set("0123456789+-*/()., ")
            allowed_words = {"sqrt", "sin", "cos", "tan", "asin", "acos", "atan", 
                           "log", "log10", "exp", "pi", "e", "ceil", "floor",
                           "abs", "round", "min", "max", "sum", "pow"}
            
            # Quick safety check
            for char in expression:
                if char not in allowed_chars and not char.isalpha() and char not in "_":
                    return {"error": f"Invalid character in expression: {char}"}

            result = eval(expression, safe_dict, {})
            return {
                "expression": expression,
                "result": round(result, precision) if isinstance(result, float) else result,
                "precision": precision,
            }
        except ZeroDivisionError:
            return {"error": "Division by zero"}
        except Exception as e:
            return {"error": f"Evaluation error: {str(e)}"}

    def _system_info_handler(self, detail: str = "basic") -> Dict[str, Any]:
        """
        Get system information.
        
        Args:
            detail: "basic", "full", or "python"
        """
        self.context.permissions.check("system_info")

        if detail == "python":
            return {
                "python_version": platform.python_version(),
                "python_implementation": platform.python_implementation(),
                "python_compiler": platform.python_compiler(),
            }

        info = {
            "os": platform.system(),
            "os_version": platform.version(),
            "os_release": platform.release(),
            "architecture": platform.machine(),
            "processor": platform.processor(),
            "python_version": platform.python_version(),
            "hostname": platform.node(),
        }

        if detail == "full":
            try:
                import psutil
                info["cpu_count"] = psutil.cpu_count()
                info["cpu_freq"] = psutil.cpu_freq()._asdict() if psutil.cpu_freq() else None
                info["memory"] = psutil.virtual_memory()._asdict()
                info["disk"] = psutil.disk_usage("/")._asdict()
            except ImportError:
                info["psutil"] = "not available"

        return info

    def _time_util_handler(self, operation: str = "now", **kwargs) -> Dict[str, Any]:
        """
        Time/date utility operations.
        
        Args:
            operation: "now", "format", "parse", "duration"
            **kwargs: Additional arguments based on operation
        """
        time_format = self.context.config.get("time_format", "%Y-%m-%d %H:%M:%S")

        if operation == "now":
            return {
                "timestamp": time.time(),
                "formatted": datetime.datetime.now().strftime(time_format),
                "iso": datetime.datetime.now().isoformat(),
                "utc": datetime.datetime.utcnow().isoformat() + "Z",
            }

        elif operation == "format":
            timestamp = kwargs.get("timestamp", time.time())
            fmt = kwargs.get("format", time_format)
            dt = datetime.datetime.fromtimestamp(timestamp)
            return {
                "timestamp": timestamp,
                "formatted": dt.strftime(fmt),
            }

        elif operation == "parse":
            date_string = kwargs.get("date_string")
            fmt = kwargs.get("format", time_format)
            try:
                dt = datetime.datetime.strptime(date_string, fmt)
                return {
                    "parsed": True,
                    "timestamp": dt.timestamp(),
                    "iso": dt.isoformat(),
                }
            except ValueError as e:
                return {"error": f"Parse error: {e}"}

        elif operation == "duration":
            start = kwargs.get("start")
            end = kwargs.get("end", time.time())
            if start is None:
                return {"error": "start timestamp required"}
            diff = end - start
            return {
                "seconds": diff,
                "minutes": diff / 60,
                "hours": diff / 3600,
                "days": diff / 86400,
                "human": self._format_duration(diff),
            }

        else:
            return {"error": f"Unknown operation: {operation}"}

    def _format_duration(self, seconds: float) -> str:
        """Format duration in human-readable form."""
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            return f"{seconds/60:.1f}m"
        elif seconds < 86400:
            return f"{seconds/3600:.1f}h"
        else:
            return f"{seconds/86400:.1f}d"