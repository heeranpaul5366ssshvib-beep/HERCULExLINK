# Issue 002 — Model Adapter Interface & Routing

Priority: High
Estimate: 1–2 person-weeks

Goal
- Define and implement a `models/adapters` contract and a routing policy to select local/remote models with fallback.

Acceptance criteria
- `models/adapters/base_adapter.py` contains a clear interface for `chat`, `embeddings`, and `health` methods.
- A simple routing policy implementation that chooses adapters by capability and health.
- Unit tests for routing and a mock adapter.

Files to change (suggested)
- `models/adapters/base_adapter.py` — ensure interface completeness
- `models/adapters` — add a `router.py` or `manager` implementation
- `models/ollama_adapter.py` — ensure it implements the full adapter interface
