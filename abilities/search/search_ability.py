from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Search Ability (internal + web)
Author: Heeran Paul
License: MIT
--------------------------------------------

Backward compatible: ``execute(query, knowledge_manager)`` still
searches internal knowledge. Pass ``source="web"`` (or omit the
manager) for real internet search:

    ability.execute("latest PyTorch release", source="web")

Web providers (first configured wins, DuckDuckGo needs no key):
  1. Tavily  (env TAVILY_API_KEY)
  2. Brave   (env BRAVE_API_KEY)
  3. DuckDuckGo instant answers (keyless, rate-limited)

Safety: private/loopback/link-local hosts are never fetched;
responses are size-capped; raw HTML is stripped to text.
"""

import html
import json
import os
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from abilities.base_ability import BaseAbility

_DEFAULT_TIMEOUT_S = 15
_MAX_RESULTS = 5
_MAX_FETCH_BYTES = 2 * 1024 * 1024

# Hosts/IPs that must never be fetched (SSRF guard).
_BLOCKED_HOSTS = {
    "localhost", "127.0.0.1", "::1", "0.0.0.0",
    "169.254.169.254",  # cloud instance metadata
    "metadata.google.internal",
}

_PRIVATE_PREFIXES = (
    "10.", "172.16.", "172.17.", "172.18.", "172.19.", "172.20.",
    "172.21.", "172.22.", "172.23.", "172.24.", "172.25.", "172.26.",
    "172.27.", "172.28.", "172.29.", "172.30.", "172.31.",
    "192.168.", "127.", "169.254.",
)


class _TextExtractor(HTMLParser):
    """Minimal HTML -> text (drops script/style, collapses whitespace)."""

    def __init__(self):
        super().__init__()
        self._chunks: list = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            text = data.strip()
            if text:
                self._chunks.append(text)

    def text(self, limit: int = 8000) -> str:
        out = re.sub(r"\s+", " ", " ".join(self._chunks)).strip()
        return out[:limit]


def _host_blocked(url: str) -> bool:
    try:
        host = urllib.parse.urlparse(url).hostname or ""
    except Exception:
        return True
    host = host.lower().rstrip(".")
    if host in _BLOCKED_HOSTS or host.endswith(".onion"):
        return True
    return host.startswith(_PRIVATE_PREFIXES)


def _http_get(url: str, timeout_s: int, headers: dict | None = None) -> tuple:
    """GET with size cap. Returns (status_code, body_bytes)."""
    req = urllib.request.Request(url, headers={
        "User-Agent": "HERCULE-Search/1.0 (+research tool)",
        **(headers or {}),
    })
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        body = resp.read(_MAX_FETCH_BYTES + 1)
        return resp.status, body[:_MAX_FETCH_BYTES]


def _search_duckduckgo(query: str, max_results: int, timeout_s: int) -> list:
    params = urllib.parse.urlencode(
        {"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"})
    _, body = _http_get(f"https://api.duckduckgo.com/?{params}", timeout_s)
    try:
        payload = json.loads(body.decode("utf-8", errors="replace"))
    except Exception:
        return []
    results = []
    for topic in payload.get("RelatedTopics", []):
        if isinstance(topic, dict) and topic.get("FirstURL"):
            results.append({
                "title": html.unescape(topic.get("Text", "")[:120]),
                "url": topic.get("FirstURL", ""),
                "snippet": html.unescape(topic.get("Text", "")),
            })
        elif isinstance(topic, dict):  # grouped topics
            for sub in topic.get("Topics", []):
                if sub.get("FirstURL"):
                    results.append({
                        "title": html.unescape(sub.get("Text", "")[:120]),
                        "url": sub.get("FirstURL", ""),
                        "snippet": html.unescape(sub.get("Text", "")),
                    })
        if len(results) >= max_results:
            break
    abstract = payload.get("AbstractText", "")
    if abstract:
        results.insert(0, {
            "title": payload.get("Heading", query),
            "url": payload.get("AbstractURL", ""),
            "snippet": abstract,
        })
    return results[:max_results]


def _search_tavily(query: str, max_results: int, timeout_s: int) -> list:
    key = os.environ.get("TAVILY_API_KEY", "")
    if not key:
        return []
    data = json.dumps({"api_key": key, "query": query,
                       "max_results": max_results}).encode()
    req = urllib.request.Request(
        "https://api.tavily.com/search",
        data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        payload = json.loads(resp.read(_MAX_FETCH_BYTES).decode("utf-8"))
    return [{"title": r.get("title", ""), "url": r.get("url", ""),
             "snippet": r.get("content", "")}
            for r in payload.get("results", [])][:max_results]


def _search_brave(query: str, max_results: int, timeout_s: int) -> list:
    key = os.environ.get("BRAVE_API_KEY", "")
    if not key:
        return []
    params = urllib.parse.urlencode({"q": query, "count": max_results})
    _, body = _http_get(f"https://api.search.brave.com/res/v1/web/search?{params}",
                        timeout_s, headers={"X-Subscription-Token": key})
    payload = json.loads(body.decode("utf-8", errors="replace"))
    return [{"title": r.get("title", ""), "url": r.get("url", ""),
             "snippet": r.get("description", "")}
            for r in payload.get("web", {}).get("results", [])][:max_results]


def web_search(query: str, max_results: int = _MAX_RESULTS,
               timeout_s: int = _DEFAULT_TIMEOUT_S) -> list:
    """Internet search. Tries keyed providers first, falls back to DuckDuckGo."""
    query = str(query or "").strip()
    if not query:
        return []
    for provider in (_search_tavily, _search_brave, _search_duckduckgo):
        try:
            results = provider(query, max_results, timeout_s)
        except Exception:
            continue
        if results:
            return results
    return []


def fetch_url(url: str, timeout_s: int = _DEFAULT_TIMEOUT_S,
              text_limit: int = 8000) -> dict:
    """Fetch a page and return stripped text. SSRF-guarded, size-capped."""
    url = str(url or "").strip()
    if not url or _host_blocked(url):
        return {"status": "failed", "error": "blocked or invalid URL"}
    scheme = urllib.parse.urlparse(url).scheme.lower()
    if scheme not in ("http", "https"):
        return {"status": "failed", "error": f"unsupported scheme: {scheme}"}
    try:
        status, body = _http_get(url, timeout_s)
        if status != 200:
            return {"status": "failed", "error": f"HTTP {status}"}
        parser = _TextExtractor()
        parser.feed(body.decode("utf-8", errors="replace"))
        return {"status": "success", "url": url, "text": parser.text(text_limit)}
    except Exception as exc:
        return {"status": "failed", "error": f"{type(exc).__name__}: {exc}"[:200]}


class SearchAbility(BaseAbility):

    def __init__(self):

        super().__init__(

            "search",

            "Search internal knowledge and the internet",

            capability="RESEARCH",
            inputs={"query": "search string", "source": "internal|web|auto",
                    "max_results": "max web hits", "url": "page to fetch"},
            outputs={"results": "ranked hits with title/url/snippet",
                     "text": "fetched page text"},
            permissions=["RESEARCH"],
            verification="hits carry title+url; fetch returns stripped text",
            timeout_s=_DEFAULT_TIMEOUT_S,
            risk="MEDIUM",

        )

    ##################################################

    def execute(

        self,

        query,

        knowledge_manager=None,

        source: str = "auto",

        max_results: int = _MAX_RESULTS,

        url: str = "",

        timeout_s: int | None = None,

    ):

        # Page fetch mode.
        if url:
            return fetch_url(url, timeout_s or self.timeout_s)

        source = str(source or "auto").lower()
        if source == "web" or (source == "auto" and knowledge_manager is None):
            try:
                results = web_search(query, max(1, min(int(max_results), 10)),
                                     timeout_s or self.timeout_s)
            except Exception as exc:
                return {"status": "failed",
                        "error": f"{type(exc).__name__}: {exc}"[:200]}
            return {"status": "success", "source": "web",
                    "query": str(query), "results": results}

        # Internal knowledge (original behavior).
        try:
            hits = knowledge_manager.retrieve(query)
        except Exception as exc:
            return {"status": "failed",
                    "error": f"{type(exc).__name__}: {exc}"[:200]}
        if isinstance(hits, dict) and "status" in hits:
            return hits
        return {"status": "success", "source": "internal",
                "query": str(query), "results": hits}
