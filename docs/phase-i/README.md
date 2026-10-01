# Phase I — Reproducible Environment + Production Cutover

## What changed

- `requirements-lock.txt`: exact verified set (51 pins, win-amd64,
  Python 3.14.6); `requirements.txt` keeps portable floors + pointer.
- `system/config/env_validation.py`: read-only `validate_environment`
  (python, package floors, vector/embedding backends, devices, static
  config check). Installs nothing.
- `system/startup_validation.py`: fail-fast gate classifying
  configuration_error / backend_unavailable / runtime_failure;
  `RuntimeInitializer.initialize(embedding_config=...)` enforces it.
- `EmbeddingManager`: `use_cache`, `tracer`, `timeout_s` options;
  `models/embeddings/routing.py`: router-authoritative
  `select_embedding_model` / `route_and_embed` (raises when the manager
  lacks the routed model — never substitutes).
- `config/hercule.example.json`: production embeddings reference.
- `asyncio_default_fixture_loop_scope = "function"` pinned in
  pyproject (notice resolved, nothing suppressed).
- Docs: `environment.md`, `production-cutover.md`, ADR-007.

## Production path

`{"mode": "production"}` → MiniLM-L6-v2 (384-dim, cpu) via
`resolve → validate_startup → services["embeddings"]`, with model/dim
in every chunk's metadata + provenance and index-manifest
compatibility enforced on load. CI (`HERCULE_MODE=ci`) stays hash;
offline stays hermetic; hash fails closed in production.
