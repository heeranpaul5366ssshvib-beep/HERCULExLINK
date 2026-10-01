from __future__ import annotations
"""
HERCULE AI Operating System
Module: Web Ability
Author: Heeran Paul
License: MIT

Real implementation: HTTP requests, web scraping, API calls with security.
"""

import json
import re
import time
import urllib.parse
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from abilities.base_ability import BaseAbility


@dataclass
class WebRequest:
    url: str
    method: str = "GET"
    headers: Optional[Dict[str, str]] = None
    data: Optional[str] = None
    timeout: int = 30
    follow_redirects: bool = True
    max_redirects: int = 5


@dataclass
class WebResponse:
    status_code: int
    headers: Dict[str, str]
    content: str
    url: str
    elapsed_ms: float


class WebAbility(BaseAbility):

    BLOCKED_DOMAINS = {
        "localhost", "127.0.0.1", "0.0.0.0", "::1",
        "169.254.169.254",  # AWS metadata
        "metadata.google.internal",  # GCP metadata
    }
    BLOCKED_IPS = {
        "127.0.0.1", "0.0.0.0", "::1",
        "169.254.169.254",
        "10.", "172.16.", "172.17.", "172.18.", "172.19.",
        "172.20.", "172.21.", "172.22.", "172.23.",
        "172.24.", "172.25.", "172.26.", "172.27.",
        "172.28.", "172.29.", "172.30.", "172.31.",
        "192.168.",
    }

    def __init__(self):

        super().__init__(
            "web",
            "Web information retrieval via HTTP/HTTPS",
            capability="WEB_SEARCH",
            inputs={
                "operation": "get|post|put|delete|patch|head|options",
                "url": "target URL (http/https only)",
                "headers": "optional request headers",
                "data": "request body for POST/PUT/PATCH",
                "params": "query parameters as dict",
                "timeout": "request timeout in seconds (default 30)",
            },
            outputs={
                "status_code": "HTTP status code",
                "headers": "response headers",
                "content": "response body",
                "url": "final URL after redirects",
                "elapsed_ms": "request duration",
            },
            permissions=["WEB_SEARCH", "NETWORK_ACCESS"],
            environments={"default"},
            verification="valid HTTP response, content returned",
            timeout_s=60,
            risk="MEDIUM",
        )
        self._session_cookies: Dict[str, str] = {}
        self._request_count = 0
        self._last_request_time = 0.0

    def _is_blocked(self, url: str) -> Optional[str]:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return f"scheme '{parsed.scheme}' not allowed (http/https only)"
        hostname = parsed.hostname or ""
        if hostname in self.BLOCKED_DOMAINS:
            return f"blocked domain: {hostname}"
        for blocked_ip in self.BLOCKED_IPS:
            if hostname.startswith(blocked_ip):
                return f"blocked IP range: {blocked_ip}"
        if re.match(r"^10\.\d+\.\d+\.\d+$", hostname):
            return "blocked private IP range (10.x)"
        if re.match(r"^192\.168\.\d+\.\d+$", hostname):
            return "blocked private IP range (192.168.x)"
        if re.match(r"^172\.(1[6-9]|2[0-9]|3[0-1])\.\d+\.\d+$", hostname):
            return "blocked private IP range (172.16-31.x)"
        return None

    def _rate_limit(self):
        now = time.time()
        if now - self._last_request_time < 0.1:  # 10 req/s max
            time.sleep(0.1 - (now - self._last_request_time))
        self._last_request_time = time.time()
        self._request_count += 1

    def validate_input(self, task, **kwargs):
        if isinstance(task, dict):
            url = task.get("url", "")
            if not url:
                return "url is required"
            blocked = self._is_blocked(url)
            if blocked:
                return blocked
            return ""
        text = str(task or "")
        urls = re.findall(r'https?://[^\s]+', text)
        if not urls:
            return "no valid URL found in request"
        for url in urls:
            blocked = self._is_blocked(url)
            if blocked:
                return blocked
        return ""

    def execute(self, task, context=None, **kwargs) -> Dict[str, Any]:
        if isinstance(task, dict):
            operation = str(task.get("operation", "get")).upper()
            url = task.get("url", "")
            headers = task.get("headers") or {}
            data = task.get("data")
            params = task.get("params")
            timeout = int(task.get("timeout", 30))
        else:
            operation = "GET"
            urls = re.findall(r'https?://[^\s]+', str(task))
            if not urls:
                return {"status": "failed", "error": "no URL provided"}
            url = urls[0]
            headers = {}
            data = None
            params = None
            timeout = 30

        if params:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}{urllib.parse.urlencode(params)}"

        blocked = self._is_blocked(url)
        if blocked:
            return {"status": "failed", "error": blocked}

        self._rate_limit()

        request = WebRequest(
            url=url,
            method=operation,
            headers=headers,
            data=data,
            timeout=timeout,
        )

        try:
            response = self._send_request(request)
            return {
                "status": "success",
                "operation": operation.lower(),
                "status_code": response.status_code,
                "headers": response.headers,
                "content": response.content,
                "url": response.url,
                "elapsed_ms": response.elapsed_ms,
            }
        except urllib.error.HTTPError as exc:
            return {
                "status": "failed",
                "error": f"HTTP {exc.code}: {exc.reason}",
                "status_code": exc.code,
                "url": url,
            }
        except urllib.error.URLError as exc:
            return {"status": "failed", "error": f"URL error: {exc.reason}", "url": url}
        except Exception as exc:
            return {"status": "failed", "error": str(exc)[:300], "url": url}

    def _send_request(self, request: WebRequest) -> WebResponse:
        start = time.perf_counter()
        req = urllib.request.Request(
            request.url,
            data=request.data.encode("utf-8") if request.data else None,
            method=request.method,
        )
        default_headers = {
            "User-Agent": "HERCULE/1.0 (WebAbility)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        for k, v in default_headers.items():
            req.add_header(k, v)
        for k, v in (request.headers or {}).items():
            req.add_header(k, v)
        for cookie_name, cookie_value in self._session_cookies.items():
            req.add_header("Cookie", f"{cookie_name}={cookie_value}")

        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(),
            urllib.request.HTTPRedirectHandler() if request.follow_redirects else urllib.request.HTTPHandler(),
        )

        with opener.open(req, timeout=request.timeout) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
            headers = dict(resp.headers)
            final_url = resp.geturl()
            for cookie in resp.headers.get_all("Set-Cookie", []):
                name_val = cookie.split(";")[0].split("=", 1)
                if len(name_val) == 2:
                    self._session_cookies[name_val[0].strip()] = name_val[1].strip()

        elapsed = (time.perf_counter() - start) * 1000
        return WebResponse(
            status_code=resp.status,
            headers=headers,
            content=content,
            url=final_url,
            elapsed_ms=elapsed,
        )