# Capability → File Mapping (scan results)

This file maps each high-level capability area to repository files that implement or relate to it (first-pass, produced by code scan).

## Memory
- memory/memory_manager.py — orchestrates short/working/long-term/episodic/procedural memories
- memory/vector/vector_manager.py, memory/vector/vector_memory.py — vector memory manager placeholder
- memory/episodic/episodic_memory.py — episodic memory
- memory/long_term/long_term_memory.py — long-term storage
- memory/short_term/short_term_memory.py — short-term memory APIs
- memory/retrieval/retrival_engine.py — retrieval engine (note: spelling 'retrival')
- knowledge/embeddings/embedding_index.py — embedding index utility
- knowledge/knowledge_manager.py, knowledge/retrieval/knowledge_retriever.py — knowledge retrieval

## Models & Embeddings
- models/adapters/base_adapter.py — model adapter interface
- models/adapters/ollama_adapter.py, models/ollama/client.py — example adapter(s)
- models/embeddings/embedding_manager.py — embedding manager
- models/prompts/prompt_manager.py — prompt management utilities

## Agents & Orchestration
- agents/agent_manager.py, agents/agent_registry.py, agents/agent_scheduler.py — agent lifecycle and scheduling
- agents/*_agent.py (planner_agent.py, executor_agent.py, vision_agent.py, etc.) — domain agents
- orchestrator/orchestrator.py, orchestrator/executor.py, orchestrator/dispatcher.py — orchestration pipeline
- orchestrator/agent.py — orchestrator agent wrapper

## Perception (Vision / Audio)
- perception/perception_manager.py — perception manager
- perception/vision/vision_processor.py — vision processing
- perception/audio/audio_processor.py, perception/speech/ — speech subpackages
- perception/multimodal/multimodal_processor.py — combined pipelines

## System Control / Automation
- abilities/system_control/system_control_ability.py — system control ability
- system/ and scripts/ — assorted system utilities and orchestrator scripts

## Developer Tools & Coding Intelligence
- developer_tools/* — architecture validator, integration tester, code analyzers
- coding_agent.py and abilities/coding/ — coding orchestration

## Security, Monitoring, Observability
- security/* — security primitives
- developer_tools/health_monitor.py — monitoring utilities

## Runtime & Init
- runtime/initializer.py, runtime/runtime.py, runtime/validator.py — startup/runtime glue

## Tests
- tests/test_memory.py, tests/test_orchestrator.py, tests/test_brain.py — existing unit tests to extend

## Notable Gaps (confirmed by scan)
- Vector DB backend integration (e.g., FAISS/Chroma/Milvus) not present; `memory/vector` has manager but no concrete DB adapter.
- Embedding runtime/service: adapters exist for Ollama, but a generic embedding pipeline and local embedder choice is incomplete.
- ASR/TTS implementations are not present; `perception/speech` is scaffolded but lacks full adapters.
- OCR/screen-capture adapter not implemented; `vision_processor` exists but needs model connectors.
- System-control sandbox & permission enforcement needs expansion beyond the ability wrapper.
- Human-approval UI and audit/logging endpoints are not found.

---

Use this file to drive issue creation and prioritization for the minimal vertical.
