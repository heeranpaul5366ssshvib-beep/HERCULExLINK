# Implementation Roadmap — HERCULE JARVIS

This roadmap organizes work into phases, milestones, and rough effort estimates (person-weeks). Adjust estimates per team size and velocity.

## Phase A — Discovery & Foundation (2–4 pw)
- Milestone A1: Requirements refinement & success metrics — 0.5 pw
- Milestone A2: Architecture design & component contracts — 1 pw
- Milestone A3: Developer experience + CI scaffolding — 0.5–2 pw

## Phase B — Core Systems (6–12 pw)
- Milestone B1: Memory subsystem (vector store, indexing, retrieval API) — 2–4 pw
- Milestone B2: Agent orchestration (agent manager, scheduler, registry) — 2–3 pw
- Milestone B3: Model integration layer (local LLM adapters, routing) — 2–4 pw

## Phase C — Perception & Interfaces (6–10 pw)
- Milestone C1: Conversational stack (ASR/TTS pipeline, dialog context) — 2–4 pw
- Milestone C2: Vision stack (screen OCR, UI element detection, camera pipeline) — 2–4 pw
- Milestone C3: System control adapters (process/window/file automation) — 1–2 pw

## Phase D — Autonomy, Planning & Execution (6–12 pw)
- Milestone D1: Planner + decision engine (goal→plan→actions) — 2–4 pw
- Milestone D2: Executor (tool adapters, verification, retries) — 2–4 pw
- Milestone D3: Safety & approval gates (human-in-the-loop) — 1–4 pw

## Phase E — Specialized Capabilities & Integrations (Ongoing)
- Coding intelligence, data pipelines, scientific modules, diagnostics — incremental (each 1–6 pw)

## Cross-cutting (Continuous)
- Security, monitoring, test harness, performance profiling, UX/feedback loops

---

Notes:
- pw = person-weeks. Estimates are coarse; refine after Discovery.
- Prioritize a minimal vertical (memory + model adapter + one agent + UI) for early validation.
