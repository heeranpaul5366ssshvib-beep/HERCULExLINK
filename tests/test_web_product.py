from __future__ import annotations
"""Web product tests (Phase 9L/9M): auth, isolation, rate limit, chat,
streaming, benchmark portal. Server binds loopback ephemeral port."""

import json
import threading
import urllib.request

import pytest

import web.server as srv


@pytest.fixture(scope="module")
def server():
    srv._sessions.clear()
    http = srv.run(port=0)
    port = http.server_address[1]
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    http.shutdown()


def _req(base, path, token=None, data=None):
    req = urllib.request.Request(base + path,
                                 data=json.dumps(data).encode() if data else None,
                                 headers={"Content-Type": "application/json",
                                          **({"X-Auth-Token": token} if token else {})},
                                 method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def test_public_pages_need_no_auth(server):
    for path in ("/", "/benchmarks", "/docs", "/safety", "/model-card"):
        code, _ = _req(server, path)
        assert code == 200, path


def test_api_requires_auth(server):
    code, _ = _req(server, "/api/reports/phase6_eval.json")
    assert code == 401
    code, body = _req(server, "/api/reports/phase6_eval.json", token="wrong")
    assert code == 401


def test_reports_served_with_auth(server):
    code, body = _req(server, "/api/reports/phase6_eval.json", token=srv.TOKEN)
    assert code == 200
    assert json.loads(body)["reference_ceiling" if "reference_ceiling" in json.loads(body) else "reference"] is not None


def test_chat_roundtrip_and_demo_label(server):
    code, body = _req(server, "/api/chat", token=srv.TOKEN,
                       data={"message": "hello"})
    assert code == 200
    out = json.loads(body)
    assert "demo responder" in out["backend"]  # no checkpoint configured
    assert out["text"]


def test_session_isolation(server):
    import uuid

    other = "tok-" + uuid.uuid4().hex
    srv._sessions[other] = {"history": [], "hits": [], "created": 0.0}
    _req(server, "/api/chat", token=srv.TOKEN, data={"message": "aaa"})
    assert srv._sessions[srv.TOKEN]["history"] != srv._sessions[other]["history"]
    del srv._sessions[other]


def test_rate_limit_enforced(server):
    srv.RATE_LIMIT if False else None
    import web.server as _s

    old, _s.RATE_LIMIT = _s.RATE_LIMIT, 2
    try:
        srv._sessions[srv.TOKEN]["hits"] = []
        codes = [_req(server, "/api/chat", token=srv.TOKEN,
                      data={"message": "x"})[0] for _ in range(4)]
        assert 429 in codes
    finally:
        _s.RATE_LIMIT = old
        srv._sessions[srv.TOKEN]["hits"] = []


def test_stream_endpoint(server):
    code, body = _req(server, "/api/chat/stream", token=srv.TOKEN)
    assert code == 200
    assert b"data:" in body and b"done" in body


def test_non_loopback_bind_refused():
    with pytest.raises(RuntimeError, match="loopback"):
        srv.run(host="0.0.0.0", port=18765)
