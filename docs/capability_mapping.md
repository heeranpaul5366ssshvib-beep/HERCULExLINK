# Capability Mapping — Spec → Code

This file maps high-level capability groups to existing repository locations and highlights gaps.

## Mapping (current repository)
- Core Intelligence: `intelligence/`, `brain/`, `planner.py`, `reasoning_engine.py`, `decision_engine.py` — existing foundation for reasoning and planners.
- Conversational Intelligence: `communication/`, `communication/communication_manager.py`, `communication/api/` — supports text/console/web interfaces; limited speech support.
- Autonomous Agents: `agents/`, `agent_manager.py`, `agent_registry.py`, `agent_scheduler.py`, `base_agent.py`, `coding_agent.py` — strong agent scaffolding present.
- Memory System: `memory/`, `knowledge/`, `data/knowledge/`, `data/memory/` — storage exists but vector memory and ranking APIs not yet implemented.
- Perception / Vision: `perception/`, `vision_agent.py` — skeletons exist but no integrated OCR/model runtime adapters.
- System / Computer Control: `system/`, `scripts/`, `orchestrator/` — basic utilities present; desktop automation adapters are missing.
- Coding Intelligence: `developer_tools/`, `coding_agent.py`, `examples/` — many developer utilities and analyzers available.
- Research & Knowledge: `knowledge/`, `search/`, `research/`, `data/` — document and search utilities exist but semantic search and QA pipelines need work.
- Security & Monitoring: `security/`, `developer_tools/health_monitor.py` — early diagnostics exist; authentication/authorization and hardened audit trails are gaps.

## Identified Gaps (high priority)
- Vector store & embedding pipeline (local or integrated vector DB)
- Local LLM adapters and model routing/fallback logic
- ASR/TTS pipelines (speech capture and synthesis)
- Robust vision adapters (OCR, UI-object detection models)
- System control sandboxing and permission model
- Human-in-the-loop approval UI and audit logging
- End-to-end QA and integration tests for long-running agent workflows

## Suggested short-term wins
- Implement a minimal vector store wrapper and embedder adapter.
- Add a model-adapter interface for local LLMs (mockable) and a simple routing policy.
- Wire `agent_manager` to the memory API for retrieval-augmented decisions.
