from __future__ import annotations
"""
HERCULE AI Operating System
Module: Browser Ability
Author: Heeran Paul
License: MIT

Real implementation: Browser automation via Playwright.
Supports navigation, screenshots, clicks, typing, extraction.
"""

import json
import os
import tempfile
import time
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from abilities.base_ability import BaseAbility


@dataclass
class BrowserAction:
    action: str  # navigate, click, type, screenshot, extract, wait, evaluate
    selector: Optional[str] = None
    url: Optional[str] = None
    text: Optional[str] = None
    value: Optional[str] = None
    timeout: int = 30000
    options: Optional[Dict[str, Any]] = None


class BrowserAbility(BaseAbility):

    def __init__(self):
        super().__init__(
            "browser",
            "Browser automation: navigate, click, type, screenshot, extract",
            capability="BROWSER_USE",
            inputs={
                "operation": "navigate|click|type|screenshot|extract|wait|evaluate",
                "url": "target URL for navigate",
                "selector": "CSS selector for click/type/extract",
                "text": "text to type",
                "value": "value for select/options",
                "timeout": "action timeout in ms (default 30000)",
                "options": "additional options dict",
            },
            outputs={
                "content": "extracted content or screenshot path",
                "url": "current page URL",
                "title": "page title",
                "cookies": "browser cookies",
            },
            permissions=["BROWSER_USE", "APPLICATION_CONTROL"],
            environments={"default"},
            verification="action completed, evidence captured",
            timeout_s=120,
            risk="MEDIUM",
        )
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._initialized = False

    def _ensure_playwright(self):
        if self._initialized:
            return True
        try:
            from playwright.sync_api import sync_playwright
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=True)
            self._context = self._browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="HERCULE/1.0 BrowserAbility",
            )
            self._page = self._context.new_page()
            self._initialized = True
            return True
        except ImportError:
            return False
        except Exception as exc:
            return False

    def validate_input(self, task, **kwargs):
        if isinstance(task, dict):
            op = task.get("operation", "")
            if not op:
                return "operation is required"
            if op == "navigate" and not task.get("url"):
                return "navigate requires url"
            if op in ("click", "type", "extract") and not task.get("selector"):
                return f"{op} requires selector"
            if op == "type" and not task.get("text"):
                return "type requires text"
            return ""
        text = str(task or "")
        if not text.strip():
            return "empty browser request"
        return ""

    def execute(self, task, context=None, **kwargs) -> Dict[str, Any]:
        if not self._ensure_playwright():
            return {
                "status": "failed",
                "error": "Playwright not available. Install with: pip install playwright && playwright install chromium"
            }

        if isinstance(task, dict):
            operation = str(task.get("operation", "")).lower()
            action = BrowserAction(
                action=operation,
                selector=task.get("selector"),
                url=task.get("url"),
                text=task.get("text"),
                value=task.get("value"),
                timeout=task.get("timeout", 30000),
                options=task.get("options"),
            )
        else:
            text = str(task or "").strip()
            if text.startswith("navigate "):
                operation = "navigate"
                action = BrowserAction(action="navigate", url=text[9:].strip())
            elif text.startswith("screenshot"):
                operation = "screenshot"
                action = BrowserAction(action="screenshot")
            else:
                return {"status": "failed", "error": f"unknown operation in text: {text[:50]}"}

        try:
            result = getattr(self, f"_{action.action}")(action)
            return result
        except AttributeError:
            return {"status": "failed", "error": f"unknown operation: {action.action}"}
        except Exception as exc:
            return {"status": "failed", "error": str(exc)[:500]}

    def _navigate(self, action: BrowserAction) -> Dict[str, Any]:
        if not action.url:
            return {"status": "failed", "error": "navigate requires url"}
        try:
            response = self._page.goto(action.url, timeout=action.timeout, wait_until="domcontentloaded")
            return {
                "status": "success",
                "operation": "navigate",
                "url": self._page.url,
                "title": self._page.title(),
                "status_code": response.status if response else 0,
            }
        except Exception as exc:
            return {"status": "failed", "error": str(exc)[:300]}

    def _click(self, action: BrowserAction) -> Dict[str, Any]:
        if not action.selector:
            return {"status": "failed", "error": "click requires selector"}
        try:
            self._page.click(action.selector, timeout=action.timeout)
            return {
                "status": "success",
                "operation": "click",
                "selector": action.selector,
                "url": self._page.url,
            }
        except Exception as exc:
            return {"status": "failed", "error": str(exc)[:300]}

    def _type(self, action: BrowserAction) -> Dict[str, Any]:
        if not action.selector:
            return {"status": "failed", "error": "type requires selector"}
        if not action.text:
            return {"status": "failed", "error": "type requires text"}
        try:
            self._page.fill(action.selector, action.text, timeout=action.timeout)
            return {
                "status": "success",
                "operation": "type",
                "selector": action.selector,
                "text": action.text,
                "url": self._page.url,
            }
        except Exception as exc:
            return {"status": "failed", "error": str(exc)[:300]}

    def _screenshot(self, action: BrowserAction) -> Dict[str, Any]:
        try:
            path = tempfile.mktemp(suffix=".png")
            self._page.screenshot(path=path, full_page=action.options.get("full_page", True) if action.options else True)
            with open(path, "rb") as f:
                import base64
                encoded = base64.b64encode(f.read()).decode()
            os.unlink(path)
            return {
                "status": "success",
                "operation": "screenshot",
                "content": encoded,
                "format": "base64_png",
                "url": self._page.url,
            }
        except Exception as exc:
            return {"status": "failed", "error": str(exc)[:300]}

    def _extract(self, action: BrowserAction) -> Dict[str, Any]:
        if not action.selector:
            return {"status": "failed", "error": "extract requires selector"}
        try:
            elements = self._page.query_selector_all(action.selector)
            results = []
            for el in elements:
                text = el.inner_text()
                html = el.inner_html()
                results.append({"text": text, "html": html})
            return {
                "status": "success",
                "operation": "extract",
                "selector": action.selector,
                "count": len(results),
                "results": results,
                "url": self._page.url,
            }
        except Exception as exc:
            return {"status": "failed", "error": str(exc)[:300]}

    def _wait(self, action: BrowserAction) -> Dict[str, Any]:
        try:
            if action.selector:
                self._page.wait_for_selector(action.selector, timeout=action.timeout)
                return {"status": "success", "operation": "wait", "selector": action.selector}
            elif action.url:
                self._page.wait_for_url(action.url, timeout=action.timeout)
                return {"status": "success", "operation": "wait", "url": action.url}
            else:
                time.sleep(action.timeout / 1000)
                return {"status": "success", "operation": "wait", "duration_ms": action.timeout}
        except Exception as exc:
            return {"status": "failed", "error": str(exc)[:300]}

    def _evaluate(self, action: BrowserAction) -> Dict[str, Any]:
        try:
            script = action.options.get("script") if action.options else action.text
            if not script:
                return {"status": "failed", "error": "evaluate requires script in options or text"}
            result = self._page.evaluate(script)
            return {
                "status": "success",
                "operation": "evaluate",
                "result": result,
                "url": self._page.url,
            }
        except Exception as exc:
            return {"status": "failed", "error": str(exc)[:300]}

    def close(self):
        if self._page:
            self._page.close()
        if self._context:
            self._context.close()
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
        self._initialized = False