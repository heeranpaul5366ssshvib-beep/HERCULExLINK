# Initial Implementation Tasks

This is a starter set of issues/tasks to begin development. Use as checkboxes for an initial sprint.

- [ ] Implement `memory/vector_store` wrapper and embedding pipeline — (2–3 pw)
- [ ] Add `models/adapter` interface for local LLMs and routing policy — (2 pw)
- [ ] Hook `agent_manager` to `memory` for RAG flows — (1 pw)
- [ ] Create minimal ASR/TTS pipeline (pluggable) — (2–4 pw)
- [ ] Add OCR + screen-capture adapter in `perception/` — (2 pw)
- [ ] Implement safe system-control adapters and permission checks — (1–2 pw)
- [ ] Build Planner → Executor integration tests and test harness — (2 pw)
- [ ] Add audit logging + human approval gates (UI + API) — (2 pw)
- [ ] Create end-to-end demo: one agent that answers questions using memory + LLM — (1–2 pw)
- [ ] Add CI jobs: lint, unit tests, integration smoke test — (1 pw)

Prioritize the minimal vertical: vector store + model adapter + single agent demo.
