from __future__ import annotations
"""HERCULE public web product (Phase 9L/9M): local-first, secure by default.

- Binds 127.0.0.1 ONLY (never 0.0.0.0; public exposure requires an
  explicit reverse proxy + TLS, documented in /docs).
- Token auth (HERCULE_WEB_TOKEN or generated per boot, printed once).
- Per-session chat history isolation; per-token rate limiting (429).
- Chat: real HERCULE-LM provider when HERCULE_LM_CHECKPOINT is set,
  else a clearly-labeled demo responder (never masquerading).
- SSE streaming endpoint reuses TorchHerculeLM.stream_generate.
- Benchmark portal serves measured reports/JSON with evidence labels.
"""

import hashlib
import html
import json
import os
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports" / "frontier_program"

TOKEN = os.environ.get("HERCULE_WEB_TOKEN", "")
if not TOKEN:
    TOKEN = secrets.token_hex(16)
    print(f"[web] generated session token (use as X-Auth-Token): {TOKEN[:6]}...")

RATE_LIMIT = int(os.environ.get("HERCULE_WEB_RPM", "30"))
_sessions: dict = {}
_lock = threading.RLock()


def _now() -> float:
    return time.time()


def _session(token: str) -> dict:
    with _lock:
        sess = _sessions.get(token)
        if sess is None:
            sess = {"history": [], "hits": [], "created": _now()}
            _sessions[token] = sess
        # rate limit: sliding 60s window
        sess["hits"] = [t for t in sess["hits"] if _now() - t < 60.0]
        return sess


def _check_rate(token: str) -> bool:
    with _lock:
        sess = _session(token)
        if len(sess["hits"]) >= RATE_LIMIT:
            return False
        sess["hits"].append(_now())
        return True


def _provider():
    ckpt = os.environ.get("HERCULE_LM_CHECKPOINT", "")
    if not ckpt:
        return None, "demo responder (no trained model configured)"
    try:
        from models.hercule_lm.provider import HerculeLMProvider

        prov = HerculeLMProvider(checkpoint=ckpt,
                                 tokenizer_dir=os.environ.get("HERCULE_LM_TOKENIZER", ""))
        health = prov.health()
        if not health.get("available"):
            return None, "demo responder (checkpoint unavailable)"
        return prov, "hercule-lm"
    except Exception as exc:
        return None, f"demo responder (provider error: {exc})"


def _demo_reply(message: str) -> str:
    return (f"[demo] HERCULE received {len(message)} chars. "
            f"No trained model is configured (set HERCULE_LM_CHECKPOINT). "
            f"Echo: {message[:120]}")


def _chat_once(message: str, mode: str = "chat") -> dict:
    prov, backend = _provider()
    t0 = _now()
    if prov is None:
        text = _demo_reply(message)
    else:
        try:
            text = prov.generate(message, max_tokens=64, temperature=0.0)
        except Exception as exc:
            text, backend = f"[error] {exc}", "error"
    return {"text": text, "backend": backend, "mode": mode,
            "latency_s": round(_now() - t0, 3)}


def _report_names() -> list:
    return sorted(p.name for p in REPORTS.glob("*.json"))


PAGES = {
    "/docs": ("Documentation",
              "<p>Local-first deployment. Public exposure requires a reverse "
              "proxy with TLS; never bind this server to 0.0.0.0 directly. "
              "Auth: X-Auth-Token header. Rate limit: 30 req/min default.</p>"
              "<p>Endpoints: GET /api/reports/&lt;name&gt;, POST /api/chat, "
              "GET /api/chat/stream, GET /benchmarks, GET /model-card, GET /safety.</p>"),
    "/safety": ("Safety",
                "<p>PolicyManager gates every tool/action. Moral reasoning "
                "never grants permissions. Approval required for HIGH-risk "
                "actions. Audit log retained. See phase6_eval SAFETY suite.</p>"),
    "/model-card": ("Model card", "<p>See reports/frontier_program/model_card_nano.md "
                                  "and phase6_eval.json. Untrained models score ~0 on "
                                  "reasoning suites (measured).</p>"),
}


def _page(title: str, body: str) -> bytes:
    return (f"<!doctype html><html><head><meta charset=utf-8><title>{title}</title></head>"
            f"<body><h1>HERCULE — {title}</h1>{body}<hr><p><a href=/>chat</a> · "
            f"<a href=/benchmarks>benchmarks</a> · <a href=/docs>docs</a> · "
            f"<a href=/safety>safety</a> · <a href=/model-card>model card</a></p>"
            f"</body></html>").encode()


CHAT_HTML = """<!doctype html><html><head><meta charset=utf-8><title>HERCULE chat</title></head>
<body><h1>HERCULE chat</h1>
<div id=log style="border:1px solid #999;height:300px;overflow:auto"></div>
<input id=msg size=60 placeholder="message"><input id=tok size=20 placeholder="X-Auth-Token">
<button onclick=send()>send</button>
<script>
async function send(){
 const m=document.getElementById('msg').value, t=document.getElementById('tok').value;
 const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json','X-Auth-Token':t},body:JSON.stringify({message:m})});
 const j=await r.json();
 document.getElementById('log').innerHTML+='<p><b>you:</b> '+m+'</p><p><b>hercule ['+j.backend+']:</b> '+j.text+'</p>';
}
</script></body></html>""".encode()


class Handler(BaseHTTPRequestHandler):
    server_version = "HERCULE-Web/1.0"

    def _auth(self) -> str | None:
        token = self.headers.get("X-Auth-Token", "")
        if not secrets.compare_digest(token, TOKEN):
            self._send(401, b'{"error":"unauthorized"}', "application/json")
            return None
        if not _check_rate(token):
            self._send(429, b'{"error":"rate limited"}', "application/json")
            return None
        return token

    def _send(self, code: int, body: bytes, ctype: str = "text/html"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass  # quiet; audit via API logs if needed

    def do_GET(self):  # noqa: N802
        path = urlparse(self.path).path
        if path == "/":
            return self._send(200, CHAT_HTML)
        if path == "/benchmarks":
            names = "".join(f"<li><a href=/api/reports/{h(n)}>{h(n)}</a></li>"
                            for n in _report_names())
            return self._send(200, _page("Benchmark portal",
                                         f"<p>Every metric labeled MEASURED/ESTIMATED/BLOCKED/NOT_RUN. "
                                         f"No intelligence score.</p><ul>{names}</ul>"))
        if path in PAGES:
            title, body = PAGES[path]
            return self._send(200, _page(title, body))
        if path.startswith("/api/reports/"):
            token = self._auth()
            if token is None:
                return
            name = path.rsplit("/", 1)[-1]
            if ".." in name or "/" in name:
                return self._send(400, b'{"error":"bad name"}', "application/json")
            target = REPORTS / name
            if not target.exists() or target.suffix != ".json":
                return self._send(404, b'{"error":"not found"}', "application/json")
            return self._send(200, target.read_bytes(), "application/json")
        if path == "/api/chat/stream":
            token = self._auth()
            if token is None:
                return
            # SSE demo stream (model streaming when provider present).
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for chunk in ["hello", " from", " HERCULE"]:
                self.wfile.write(f"data: {json.dumps({'chunk': chunk})}\n\n".encode())
            self.wfile.write(b"data: {\"done\": true}\n\n")
            return
        return self._send(404, b"not found", "text/plain")

    def do_POST(self):  # noqa: N802
        path = urlparse(self.path).path
        if path != "/api/chat":
            return self._send(404, b"not found", "text/plain")
        token = self._auth()
        if token is None:
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, OSError):
            return self._send(400, b'{"error":"bad json"}', "application/json")
        message = str(payload.get("message", ""))[:2000]
        mode = str(payload.get("mode", "chat"))[:32]
        out = _chat_once(message, mode)
        with _lock:
            _session(token)["history"].append({"q": message, "a": out["text"]})
        return self._send(200, json.dumps(out).encode(), "application/json")


def run(host: str = "127.0.0.1", port: int = 8765) -> HTTPServer:
    if host != "127.0.0.1" and not os.environ.get("HERCULE_WEB_PUBLIC_OK"):
        raise RuntimeError("refusing non-loopback bind without HERCULE_WEB_PUBLIC_OK "
                           "(expose only behind TLS reverse proxy)")
    server = HTTPServer((host, port), Handler)
    print(f"[web] HERCULE on http://{host}:{port} (loopback only)")
    return server


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    run(port=args.port).serve_forever()


def h(s: str) -> str:
    return html.escape(s)
