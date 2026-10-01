# High-level Architecture Diagram

This diagram shows major components and their responsibilities.

```mermaid
graph TB
  User((User)) -->|text/voice| Interface
  Interface --> Orchestrator[Orchestrator / Frontend]
  Orchestrator --> AgentMgr[Agent Manager / Scheduler]
  AgentMgr --> Agent[Agents]
  Agent -->|read/write| Memory[Memory / Vector Store]
  Agent --> Models[Model Layer]
  Models --> Embeddings[Embedding Models]
  Models --> LLMs[LLMs (local/remote)]
  Orchestrator --> Perception[Perception (Vision/ASR/TTS)]
  Agent --> SystemCtrl[System Control Adapters]
  Monitoring -->|metrics/logs| Observability[Observability & Security]
  AgentMgr --> Planner[Planner / Decision Engine]
  Planner --> Executor[Executor / Tool Adapters]

  style Interface fill:#f9f,stroke:#333,stroke-width:1px
  style AgentMgr fill:#efe,stroke:#333
  style Memory fill:#ffd,stroke:#333
```

## Component Responsibilities
- Interface: Accepts user input (text, voice, GUI) and displays responses/status.
- Orchestrator: Routes requests, enforces policies, aggregates telemetry.
- Agent Manager: Registers, schedules and supervises agents; provides lifecycle APIs.
- Agents: Domain-specialized workers (research, coding, vision, system control).
- Memory: Persistent and vectorized memory with ranking and retrieval APIs.
- Models: Hosts LLMs and embedding models; provides routing and fallback.
- Perception: ASR/TTS, OCR, vision preprocessing and annotation.
- Planner/Executor: Converts goals into plans and executes via tool adapters.
- System Control: Safe adapters for OS-level actions with permission checks.
- Observability: Logs, metrics, security monitoring, and audit trails.
