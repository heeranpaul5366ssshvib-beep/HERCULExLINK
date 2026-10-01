from __future__ import annotations
"""
--------------------------------------------
HERCULE Network Demo Plugin
Demonstrates isolated network permission
--------------------------------------------
"""

import json
import urllib.request
import urllib.error
import time
from typing import Any, Dict, List

from plugin_sdk.plugin import Plugin
from plugin_sdk.manifest import PluginCapability


class NetworkDemoPlugin(Plugin):
    """Network demo plugin - only requires network permission."""

    name = "HERCULE Network Demo"
    version = "1.0.0"
    author = "HERCULE Team"
    description = "Demonstrates isolated network permission - controlled HTTP requests only"
    plugin_id = "hercule.network_demo"
    capabilities = ["network_request", "http_client"]
    permissions = ["network"]
    configuration_schema = {
        "default_timeout": {"type": "int", "default": 10, "minimum": 1, "maximum": 60},
        "allowed_domains": {
            "type": "array",
            "items": {"type": "string"},
            "default": ["httpbin.org", "api.github.com"],
        }
    }

    def on_discover(self) -> bool:
        self.logger.info("Network demo plugin discovered")
        return True

    def on_validate(self, hercule_version: str) -> bool:
        self.logger.info("Validating against HERCULE {}".format(hercule_version))
        return True

    def on_install(self) -> bool:
        self.logger.info("Network demo plugin installed")
        return True

    def on_enable(self) -> bool:
        if not self.context:
            return False

        # Register network request tool
        self.context.tools.register_tool(
            name="http_get",
            description="Make a safe HTTP GET request to allowed domains",
            handler=self._http_get_handler,
            capability="network_request",
            permissions=["network"],
        )

        self.context.tools.register_tool(
            name="http_post",
            description="Make a safe HTTP POST request to allowed domains",
            handler=self._http_post_handler,
            capability="network_request",
            permissions=["network"],
        )

        self.logger.info("Network demo plugin enabled")
        return True

    def on_disable(self) -> bool:
        if self.context:
            self.context.tools.unregister_tool("http_get")
            self.context.tools.unregister_tool("http_post")
        self.logger.info("Network demo plugin disabled")
        return True

    def on_uninstall(self) -> bool:
        self.logger.info("Network demo plugin uninstalled")
        return True

    def on_reload(self) -> bool:
        self.logger.info("Network demo plugin reloaded")
        return True

    def health(self) -> Dict[str, Any]:
        base = super().health()
        base.update({
            "tools_registered": 2,
        })
        return base

    def execute(self, *args, **kwargs) -> Any:
        return {"status": "use_tools_instead"}

    def _is_allowed_domain(self, url: str) -> bool:
        """Check if URL domain is in allowed list."""
        allowed = self.context.config.get("allowed_domains", ["httpbin.org", "api.github.com"])
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            return any(allowed_domain in domain for allowed_domain in allowed)
        except Exception:
            return False

    def _http_get_handler(self, url: str, timeout: int = None) -> Dict[str, Any]:
        """Make HTTP GET request."""
        if not self._is_allowed_domain(url):
            return {"error": "Domain not allowed: {}".format(url)}

        if timeout is None:
            timeout = self.context.config.get("default_timeout", 10)

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "HERCULE-NetworkDemo/1.0"})
            start = time.time()
            with urllib.request.urlopen(req, timeout=timeout) as response:
                data = response.read().decode("utf-8")
                elapsed = time.time() - start
                return {
                    "url": url,
                    "status": response.status,
                    "headers": dict(response.headers),
                    "body": data[:5000],  # Limit response size
                    "elapsed_ms": round(elapsed * 1000, 2),
                }
        except urllib.error.HTTPError as e:
            return {"error": "HTTP {}: {}".format(e.code, e.reason), "url": url}
        except urllib.error.URLError as e:
            return {"error": "URL error: {}".format(e.reason), "url": url}
        except Exception as e:
            return {"error": str(e), "url": url}

    def _http_post_handler(self, url: str, data: Dict = None, timeout: int = None) -> Dict[str, Any]:
        """Make HTTP POST request."""
        if not self._is_allowed_domain(url):
            return {"error": "Domain not allowed: {}".format(url)}

        if timeout is None:
            timeout = self.context.config.get("default_timeout", 10)

        try:
            post_data = json.dumps(data or {}).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=post_data,
                headers={
                    "User-Agent": "HERCULE-NetworkDemo/1.0",
                    "Content-Type": "application/json",
                },
                method="POST"
            )
            start = time.time()
            with urllib.request.urlopen(req, timeout=timeout) as response:
                resp_data = response.read().decode("utf-8")
                elapsed = time.time() - start
                return {
                    "url": url,
                    "status": response.status,
                    "body": resp_data[:5000],
                    "elapsed_ms": round(elapsed * 1000, 2),
                }
        except urllib.error.HTTPError as e:
            return {"error": "HTTP {}: {}".format(e.code, e.reason), "url": url}
        except Exception as e:
            return {"error": str(e), "url": url}