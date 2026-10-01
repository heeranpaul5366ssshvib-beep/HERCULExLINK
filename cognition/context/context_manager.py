from __future__ import annotations
"""
============================================
HERCULE AI Operating System
Module: Context Manager
Author: HERCULE Team
License: MIT
============================================

Context Management for model calls.

Memory != Context.
- Memory: Everything HERCULE can retain (durable, unbounded)
- Context: Only information necessary for the current model call (budgeted, prioritized)

Architecture:
    Brain
     ↓
    ContextManager
     ↓
    ContextBuilder
     ↓
    ModelRouter
     ↓
    Native LM / external provider

Context Layers (priority order, highest first):
    L0: System - System prompt, identity, safety rules
    L1: Current Task - Active goal, step, plan, verification state
    L2: Active State - Working memory, short-term state, world model slice
    L3: Relevant Memory - Retrieved semantic/episodic/procedural memories
    L4: Relevant Tool Results - Recent tool outputs, normalized and compressed
    L5: Verification State - Passed/failed steps, capability states
    L6: Recent Conversation - Last N turns, compacted

Key Principles:
- Never dump all memory into the prompt
- Budget tokens per provider/model
- Priority scoring for layer inclusion
- Tool output normalization → extract → summarize → store artifact → compact
- Structured task state for checkpoint/resume
"""

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from memory.memory_manager import MemoryManager
from models.model_manager import ModelManager

logger = logging.getLogger("HERCULE.ContextManager")


# ----------------------------------------------------------------------
# Enums and Constants
# ----------------------------------------------------------------------


class ContextLayer(str, Enum):
    """Context layer priority (higher = more important, included first)."""
    SYSTEM = "system"           # L0
    CURRENT_TASK = "current_task"  # L1
    ACTIVE_STATE = "active_state"  # L2
    RELEVANT_MEMORY = "relevant_memory"  # L3
    TOOL_RESULTS = "tool_results"  # L4
    VERIFICATION_STATE = "verification_state"  # L5
    CONVERSATION = "conversation"  # L6


class ProviderType(str, Enum):
    """Model provider types with different context limits."""
    OLLAMA = "ollama"
    BUILTIN = "builtin"
    HERCULE_LM = "hercule_lm"
    MOCK = "mock"
    UNKNOWN = "unknown"


# Default context budgets per provider (tokens)
DEFAULT_CONTEXT_BUDGETS = {
    ProviderType.OLLAMA: 8192,
    ProviderType.BUILTIN: 4096,
    ProviderType.HERCULE_LM: 2048,
    ProviderType.MOCK: 4096,
    ProviderType.UNKNOWN: 2048,
}

# Layer priority weights (higher = included first when budgeting)
LAYER_PRIORITY = {
    ContextLayer.SYSTEM: 100,
    ContextLayer.CURRENT_TASK: 90,
    ContextLayer.ACTIVE_STATE: 80,
    ContextLayer.RELEVANT_MEMORY: 70,
    ContextLayer.TOOL_RESULTS: 60,
    ContextLayer.VERIFICATION_STATE: 50,
    ContextLayer.CONVERSATION: 40,
}

# Max tokens per layer (soft limits)
LAYER_MAX_TOKENS = {
    ContextLayer.SYSTEM: 1000,
    ContextLayer.CURRENT_TASK: 1500,
    ContextLayer.ACTIVE_STATE: 1000,
    ContextLayer.RELEVANT_MEMORY: 1500,
    ContextLayer.TOOL_RESULTS: 1000,
    ContextLayer.VERIFICATION_STATE: 800,
    ContextLayer.CONVERSATION: 1000,
}


# ----------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------

# Context schema version for checkpoint compatibility
CONTEXT_SCHEMA_VERSION = 1

# ----------------------------------------------------------------------
# Data Classes
# ----------------------------------------------------------------------


@dataclass
class LayerContent:
    """Content for a single context layer."""
    layer: ContextLayer
    content: str
    tokens: int
    priority: int
    metadata: Dict[str, Any] = field(default_factory=dict)
    truncated: bool = False


@dataclass
class ContextDiagnostics:
    """Optional diagnostics for observability."""
    context_tokens: int = 0
    budget: int = 0
    compression_count: int = 0
    memory_items_selected: int = 0
    tool_results_selected: int = 0
    conversation_turns_selected: int = 0
    checkpoint_id: str = ""
    layers_included: List[str] = field(default_factory=list)
    layers_truncated: List[str] = field(default_factory=list)
    provider: str = ""
    model: str = ""
    timestamp: float = field(default_factory=time.time)
    build_latency_ms: float = 0.0


@dataclass
class StructuredTaskState:
    """Structured state for checkpoint/resume."""
    goal: str = ""
    current_step: str = ""
    completed_steps: List[str] = field(default_factory=list)
    failed_steps: List[str] = field(default_factory=list)
    verified_facts: List[str] = field(default_factory=list)
    pending_actions: List[str] = field(default_factory=list)
    artifacts: Dict[str, str] = field(default_factory=dict)
    relevant_memory: List[str] = field(default_factory=list)
    step_outputs: Dict[str, str] = field(default_factory=dict)
    capability_states: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    checkpoint_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


@dataclass
class ContextCheckpoint:
    """Checkpoint for resuming long-running tasks."""
    checkpoint_id: str
    task_state: StructuredTaskState
    context_layers: Dict[ContextLayer, LayerContent]
    provider: ProviderType
    model: str
    total_tokens: int
    budget: int
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    schema_version: int = CONTEXT_SCHEMA_VERSION


@dataclass
class BuiltContext:
    """Fully built context ready for model call."""
    layers: List[LayerContent]
    total_tokens: int
    budget: int
    provider: ProviderType
    model: str
    truncated: bool = False
    truncation_details: Dict[str, Any] = field(default_factory=dict)
    diagnostics: Optional[ContextDiagnostics] = None

    def to_prompt(self) -> str:
        """Combine layers into final prompt string."""
        parts = []
        for layer in self.layers:
            if layer.content:
                parts.append(layer.content)
        return "\n\n".join(parts)


# ----------------------------------------------------------------------
# Token Counter
# ----------------------------------------------------------------------


class TokenCounter:
    """Token counter with provider-specific estimators."""

    # Conservative character-per-token ratios per provider
    CHAR_PER_TOKEN = {
        ProviderType.OLLAMA: 3.5,      # Llama/Qwen tokenizers ~3.5 chars/token
        ProviderType.BUILTIN: 3.5,     # GGUF models similar
        ProviderType.HERCULE_LM: 4.0,  # HERCULE-LM tokenizer
        ProviderType.MOCK: 4.0,
        ProviderType.UNKNOWN: 4.0,     # Conservative default
    }

    def __init__(self, provider: ProviderType = ProviderType.UNKNOWN):
        self.provider = provider
        self.char_per_token = self.CHAR_PER_TOKEN.get(provider, 4.0)

    def count(self, text: str) -> int:
        """Approximate token count using provider-specific ratio."""
        if not text:
            return 0
        return max(1, int(len(text) / self.char_per_token))

    def count_messages(self, messages: List[Dict[str, str]]) -> int:
        """Count tokens for chat messages."""
        total = 0
        for msg in messages:
            total += self.count(msg.get("content", ""))
            total += 4  # role overhead
        return total

    def set_provider(self, provider: ProviderType):
        """Update provider for token estimation."""
        self.provider = provider
        self.char_per_token = self.CHAR_PER_TOKEN.get(provider, 4.0)

    def validate_budget(self, estimated_tokens: int, budget: int, safety_margin: float = 0.1) -> Tuple[bool, int]:
        """Validate that estimated tokens fit within budget with safety margin."""
        max_allowed = int(budget * (1 - safety_margin))
        return estimated_tokens <= max_allowed, max_allowed


# ----------------------------------------------------------------------
# Tool Output Normalizer
# ----------------------------------------------------------------------


class ToolOutputNormalizer:
    """Normalize and compress tool outputs for context inclusion."""

    @staticmethod
    def normalize(result: Any, max_tokens: int = 500) -> str:
        """Normalize tool output to compact string."""
        if result is None:
            return ""

        # Handle dict results (typical ability results)
        if isinstance(result, dict):
            return ToolOutputNormalizer._normalize_dict(result, max_tokens)

        # Handle list results
        if isinstance(result, list):
            return ToolOutputNormalizer._normalize_list(result, max_tokens)

        # Handle string results
        if isinstance(result, str):
            return ToolOutputNormalizer._truncate(result, max_tokens)

        # Fallback
        return ToolOutputNormalizer._truncate(str(result), max_tokens)

    @staticmethod
    def _normalize_dict(result: Dict[str, Any], max_tokens: int) -> str:
        """Normalize dict result, extracting key info."""
        # Extract status
        status = result.get("status", "unknown")
        parts = [f"status: {status}"]

        # Extract content/response
        for key in ("content", "response", "result", "output", "data"):
            if key in result and result[key]:
                content = str(result[key])
                if len(content) > 200:
                    content = content[:200] + "..."
                parts.append(f"{key}: {content}")
                break

        # Extract error if failed
        if status == "failed" or "error" in result:
            error = result.get("error", "")
            if error:
                parts.append(f"error: {error[:200]}")

        # Extract key metadata
        for key in ("path", "file", "destination", "source", "operation"):
            if key in result and result[key]:
                parts.append(f"{key}: {result[key]}")

        return ToolOutputNormalizer._truncate(" | ".join(parts), max_tokens)

    @staticmethod
    def _normalize_list(result: List[Any], max_tokens: int) -> str:
        """Normalize list result."""
        if not result:
            return "[]"
        items = [str(item)[:100] for item in result[:10]]
        return ToolOutputNormalizer._truncate(f"[{', '.join(items)}]", max_tokens)

    @staticmethod
    def _truncate(text: str, max_tokens: int) -> str:
        """Truncate to token budget."""
        max_chars = max_tokens * 4
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "..."


# ----------------------------------------------------------------------
# Context Builder
# ----------------------------------------------------------------------


class ContextBuilder:
    """Builds context from layers with token budgeting."""

    def __init__(
        self,
        memory_manager: MemoryManager,
        model_manager: ModelManager,
        token_counter: Optional[TokenCounter] = None,
    ):
        self.memory = memory_manager
        self.models = model_manager
        self.tokens = token_counter or TokenCounter()

    def build(
        self,
        goal: str,
        current_step: str = "",
        plan: Optional[List[Dict]] = None,
        task_state: Optional[StructuredTaskState] = None,
        tool_results: Optional[List[Dict[str, Any]]] = None,
        verification_state: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        system_prompt: str = "",
        provider: ProviderType = ProviderType.UNKNOWN,
        model: str = "",
        budget: Optional[int] = None,
        enable_diagnostics: bool = False,
    ) -> BuiltContext:
        """Build full context for a model call."""
        start_time = time.perf_counter()
        
        # Determine budget
        if budget is None:
            budget = DEFAULT_CONTEXT_BUDGETS.get(provider, 2048)

        # Update token counter for provider
        self.tokens.set_provider(provider)

        layers = []
        diagnostics = ContextDiagnostics() if enable_diagnostics else None

        if diagnostics:
            diagnostics.provider = provider.value
            diagnostics.model = model
            diagnostics.budget = DEFAULT_CONTEXT_BUDGETS.get(provider, 2048)

        layers = []

        # L0: System
        if system_prompt:
            layer = self._build_layer(
                ContextLayer.SYSTEM,
                system_prompt,
                budget,
                LAYER_MAX_TOKENS[ContextLayer.SYSTEM],
            )
            layers.append(layer)
            if diagnostics:
                diagnostics.layers_included.append(ContextLayer.SYSTEM.value)
                diagnostics.memory_items_selected += 1

        # L1: Current Task
        task_content = self._build_task_layer(goal, current_step, plan, task_state)
        if task_content:
            layer = self._build_layer(
                ContextLayer.CURRENT_TASK,
                task_content,
                budget,
                LAYER_MAX_TOKENS[ContextLayer.CURRENT_TASK],
            )
            layers.append(layer)
            if diagnostics:
                diagnostics.layers_included.append(ContextLayer.CURRENT_TASK.value)
                diagnostics.tool_results_selected += 1

        # L2: Active State
        state_content = self._build_active_state_layer(task_state)
        if state_content:
            layer = self._build_layer(
                ContextLayer.ACTIVE_STATE,
                state_content,
                budget,
                LAYER_MAX_TOKENS[ContextLayer.ACTIVE_STATE],
            )
            layers.append(layer)
            if diagnostics:
                diagnostics.layers_included.append(ContextLayer.ACTIVE_STATE.value)

        # L3: Relevant Memory
        memory_content = self._build_memory_layer(goal, task_state)
        if memory_content:
            layer = self._build_layer(
                ContextLayer.RELEVANT_MEMORY,
                memory_content,
                budget,
                LAYER_MAX_TOKENS[ContextLayer.RELEVANT_MEMORY],
            )
            layers.append(layer)

        # L4: Tool Results
        tool_content = self._build_tool_results_layer(tool_results)
        if tool_content:
            layer = self._build_layer(
                ContextLayer.TOOL_RESULTS,
                tool_content,
                budget,
                LAYER_MAX_TOKENS[ContextLayer.TOOL_RESULTS],
            )
            layers.append(layer)

        # L5: Verification State
        verify_content = self._build_verification_layer(verification_state)
        if verify_content:
            layer = self._build_layer(
                ContextLayer.VERIFICATION_STATE,
                verify_content,
                budget,
                LAYER_MAX_TOKENS[ContextLayer.VERIFICATION_STATE],
            )
            layers.append(layer)

        # L6: Conversation
        conv_content = self._build_conversation_layer(conversation_history)
        if conv_content:
            layer = self._build_layer(
                ContextLayer.CONVERSATION,
                conv_content,
                budget,
                LAYER_MAX_TOKENS[ContextLayer.CONVERSATION],
            )
            layers.append(layer)

        # Apply budget: sort by priority, include until budget exhausted
        final_layers = self._apply_budget(layers, budget, diagnostics)

        total_tokens = sum(l.tokens for l in final_layers)
        truncated = any(l.truncated for l in final_layers)
        build_latency_ms = (time.perf_counter() - start_time) * 1000

        if diagnostics:
            diagnostics.context_tokens = total_tokens
            diagnostics.budget = budget
            diagnostics.build_latency_ms = build_latency_ms
            diagnostics.layers_truncated = [l.layer.value for l in final_layers if l.truncated]
            diagnostics.compression_count = len(layers) - len(final_layers)

        return BuiltContext(
            layers=final_layers,
            total_tokens=total_tokens,
            budget=budget,
            provider=provider,
            model=model,
            truncated=truncated,
            truncation_details={
                "original_layer_count": len(layers),
                "final_layer_count": len(final_layers),
                "layers_truncated": [l.layer.value for l in final_layers if l.truncated],
            },
            diagnostics=diagnostics,
        )

    def _build_layer(
        self,
        layer: ContextLayer,
        content: str,
        budget: int,
        max_layer_tokens: int,
    ) -> LayerContent:
        """Build a layer with token counting and truncation."""
        tokens = self.tokens.count(content)
        truncated = False

        if tokens > max_layer_tokens:
            # Truncate to layer max
            max_chars = max_layer_tokens * 4
            content = content[:max_chars] + f"\n... [truncated from {tokens} tokens]"
            tokens = max_layer_tokens
            truncated = True

        return LayerContent(
            layer=layer,
            content=content,
            tokens=tokens,
            priority=LAYER_PRIORITY[layer],
            truncated=truncated,
        )

    def _apply_budget(self, layers: List[LayerContent], budget: int, diagnostics: Optional[ContextDiagnostics] = None) -> List[LayerContent]:
        """Apply token budget, keeping highest priority layers first."""
        # Sort by priority (highest first)
        sorted_layers = sorted(layers, key=lambda l: l.priority, reverse=True)

        result = []
        used = 0

        for layer in sorted_layers:
            if used + layer.tokens <= budget:
                result.append(layer)
                used += layer.tokens
            elif used < budget:
                # Try to fit a truncated version
                remaining = budget - used
                if remaining > 50:  # minimum useful tokens
                    # Truncate content
                    max_chars = remaining * 4
                    truncated_content = layer.content[:max_chars] + "\n... [budget truncated]"
                    result.append(LayerContent(
                        layer=layer.layer,
                        content=truncated_content,
                        tokens=remaining,
                        priority=layer.priority,
                        truncated=True,
                    ))
                    if diagnostics:
                        diagnostics.layers_truncated.append(layer.layer.value)
                    used = budget
                break
            else:
                if diagnostics:
                    diagnostics.layers_truncated.append(layer.layer.value)
                break

        # Restore original layer order for prompt assembly
        layer_order = {l.layer: i for i, l in enumerate(layers)}
        result.sort(key=lambda l: layer_order.get(l.layer, 999))

        return result

    def _build_task_layer(
        self,
        goal: str,
        current_step: str,
        plan: Optional[List[Dict]],
        task_state: Optional[StructuredTaskState],
    ) -> str:
        """Build L1: Current Task layer."""
        parts = [f"GOAL: {goal}"]
        if current_step:
            parts.append(f"CURRENT STEP: {current_step}")
        if task_state:
            if task_state.completed_steps:
                parts.append(f"COMPLETED: {', '.join(task_state.completed_steps[-5:])}")
            if task_state.failed_steps:
                parts.append(f"FAILED: {', '.join(task_state.failed_steps[-3:])}")
            if task_state.verified_facts:
                parts.append(f"VERIFIED: {', '.join(task_state.verified_facts[-3:])}")
        if plan:
            step_ids = [s.get("step_id", "") for s in plan if s.get("step_id")]
            if step_ids:
                parts.append(f"PLAN: {' → '.join(step_ids)}")
        return "\n".join(parts)

    def _build_active_state_layer(
        self,
        task_state: Optional[StructuredTaskState],
    ) -> str:
        """Build L2: Active State layer."""
        parts = []
        if task_state:
            if task_state.pending_actions:
                parts.append(f"PENDING: {', '.join(task_state.pending_actions[-5:])}")
            if task_state.artifacts:
                artifacts = list(task_state.artifacts.items())[-3:]
                parts.append(f"ARTIFACTS: {', '.join(f'{k}={v[:50]}' for k, v in artifacts)}")
            if task_state.capability_states:
                caps = []
                for cap, state in list(task_state.capability_states.items())[-5:]:
                    status = state.get("status", "unknown")
                    caps.append(f"{cap}={status}")
                if caps:
                    parts.append(f"CAPABILITIES: {', '.join(caps)}")
        # Working memory
        try:
            wm = self.memory.working.latest()
            if wm:
                parts.append(f"WORKING: {str(wm)[:200]}")
        except Exception:
            pass
        return "\n".join(parts)

    def _build_memory_layer(
        self,
        goal: str,
        task_state: Optional[StructuredTaskState],
    ) -> str:
        """Build L3: Relevant Memory layer."""
        parts = []

        # Retrieve relevant memories
        try:
            entities = []
            if task_state:
                entities.extend(task_state.relevant_memory)
            hits = self.memory.retrieve_relevant(
                goal,
                limit=5,
                entities=entities,
            )
            for hit in hits[:3]:
                content = hit.get("content", "")[:200]
                mtype = hit.get("memory_type", "")
                score = hit.get("score", 0)
                parts.append(f"[{mtype} score={score:.2f}] {content}")
        except Exception:
            pass

        # Explicit facts
        try:
            facts = self.memory.explicit_memories()
            if facts:
                fact_items = list(facts.items())[:3]
                parts.append("FACTS: " + "; ".join(f"{k}: {v[:100]}" for k, v in fact_items))
        except Exception:
            pass

        return "\n".join(parts)

    def _build_tool_results_layer(
        self,
        tool_results: Optional[List[Dict[str, Any]]],
    ) -> str:
        """Build L4: Tool Results layer."""
        if not tool_results:
            return ""

        parts = []
        for result in tool_results[-5:]:  # Last 5 results
            normalized = ToolOutputNormalizer.normalize(result, max_tokens=200)
            if normalized:
                parts.append(normalized)
        return "\n".join(parts)

    def _build_verification_layer(
        self,
        verification_state: Optional[Dict[str, Any]],
    ) -> str:
        """Build L5: Verification State layer."""
        if not verification_state:
            return ""

        parts = []
        passed = verification_state.get("passed_steps", 0)
        failed = verification_state.get("failed_steps", 0)
        parts.append(f"VERIFICATION: {passed} passed, {failed} failed")

        capability_states = verification_state.get("capability_states", {})
        if capability_states:
            cap_status = []
            for cap, state in list(capability_states.items())[-5:]:
                status = state.get("verification", {}).get("passed", False)
                cap_status.append(f"{cap}={'PASS' if status else 'FAIL'}")
            parts.append("CAPABILITIES: " + ", ".join(cap_status))

        return "\n".join(parts)

    def _build_conversation_layer(
        self,
        conversation_history: Optional[List[Dict[str, str]]],
    ) -> str:
        """Build L6: Recent Conversation layer."""
        if not conversation_history:
            return ""

        # Compact: keep last 4 turns, summarize older
        recent = conversation_history[-4:]
        parts = []
        for turn in recent:
            role = turn.get("role", "user")
            content = turn.get("content", "")[:300]
            parts.append(f"{role}: {content}")

        if len(conversation_history) > 4:
            parts.insert(0, f"[... {len(conversation_history) - 4} earlier turns summarized]")

        return "\n".join(parts)


# ----------------------------------------------------------------------
# Context Manager
# ----------------------------------------------------------------------


class ContextManager:
    """
    Main context management interface.

    Coordinates context building, budgeting, checkpoints, and compression.
    """

    def __init__(
        self,
        memory_manager: MemoryManager,
        model_manager: ModelManager,
        default_budget: Optional[int] = None,
    ):
        self.memory = memory_manager
        self.models = model_manager
        self.builder = ContextBuilder(memory_manager, model_manager)
        self.default_budget = default_budget
        self._checkpoints: Dict[str, ContextCheckpoint] = {}
        self._current_task_state: Optional[StructuredTaskState] = None
        self._conversation_history: List[Dict[str, str]] = []

    def build_context(
        self,
        goal: str,
        current_step: str = "",
        plan: Optional[List[Dict]] = None,
        task_state: Optional[StructuredTaskState] = None,
        tool_results: Optional[List[Dict[str, Any]]] = None,
        verification_state: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        system_prompt: str = "",
        provider: Optional[ProviderType] = None,
        model: str = "",
        budget: Optional[int] = None,
    ) -> BuiltContext:
        """Build context for current model call."""
        # Resolve provider if not specified
        if provider is None:
            provider = self._detect_provider(model)

        # Use current task state if available
        task_state = self._current_task_state

        # Use provided conversation history or fall back to internal
        conv_history = conversation_history if conversation_history is not None else self._conversation_history

        return self.builder.build(
            goal=goal,
            current_step=current_step,
            plan=plan,
            task_state=task_state,
            tool_results=tool_results,
            verification_state=verification_state,
            conversation_history=conv_history,
            system_prompt=system_prompt,
            provider=provider,
            model=model,
            budget=budget or self.default_budget,
            enable_diagnostics=True,
        )

    def _detect_provider(self, model: str) -> ProviderType:
        """Detect provider from model name."""
        if not model:
            return ProviderType.UNKNOWN
        model_lower = model.lower()
        if "ollama" in model_lower or any(m in model_lower for m in ["llama", "qwen", "mistral"]):
            return ProviderType.OLLAMA
        if "builtin" in model_lower or "gguf" in model_lower or model_lower == "hercule-local":
            return ProviderType.BUILTIN
        if "hercule" in model_lower:
            return ProviderType.HERCULE_LM
        if "mock" in model_lower:
            return ProviderType.MOCK
        return ProviderType.UNKNOWN

    # ------------------------------------------------------------------
    # Task State Management
    # ------------------------------------------------------------------

    def start_task(self, goal: str) -> StructuredTaskState:
        """Initialize task state for a new goal."""
        self._current_task_state = StructuredTaskState(goal=goal)
        self._conversation_history = []
        return self._current_task_state

    def update_task_state(
        self,
        current_step: Optional[str] = None,
        completed_step: Optional[str] = None,
        failed_step: Optional[str] = None,
        verified_fact: Optional[str] = None,
        pending_action: Optional[str] = None,
        artifact: Optional[Tuple[str, str]] = None,
        capability_state: Optional[Tuple[str, Dict[str, Any]]] = None,
    ) -> StructuredTaskState:
        """Update task state incrementally."""
        if self._current_task_state is None:
            self._current_task_state = StructuredTaskState()

        if current_step:
            self._current_task_state.current_step = current_step
        if completed_step:
            if completed_step not in self._current_task_state.completed_steps:
                self._current_task_state.completed_steps.append(completed_step)
        if failed_step:
            if failed_step not in self._current_task_state.failed_steps:
                self._current_task_state.failed_steps.append(failed_step)
        if verified_fact:
            if verified_fact not in self._current_task_state.verified_facts:
                self._current_task_state.verified_facts.append(verified_fact)
        if pending_action:
            if pending_action not in self._current_task_state.pending_actions:
                self._current_task_state.pending_actions.append(pending_action)
        if artifact:
            key, value = artifact
            self._current_task_state.artifacts[key] = value
        if capability_state:
            cap, state = capability_state
            self._current_task_state.capability_states[cap] = state

        return self._current_task_state

    def get_task_state(self) -> Optional[StructuredTaskState]:
        """Get current task state."""
        return self._current_task_state

    def clear_task(self):
        """Clear task state and conversation history."""
        self._current_task_state = None
        self._conversation_history = []

    def add_conversation_turn(self, role: str, content: str):
        """Add a conversation turn."""
        self._conversation_history.append({
            "role": role,
            "content": content,
            "timestamp": time.time(),
        })
        # Keep history bounded
        if len(self._conversation_history) > 20:
            self._conversation_history = self._conversation_history[-20:]

    # ------------------------------------------------------------------
    # Checkpoint / Resume
    # ------------------------------------------------------------------

    def create_checkpoint(
        self,
        provider: Optional[ProviderType] = None,
        model: str = "",
        budget: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ContextCheckpoint:
        """Create a context checkpoint for resume."""
        if self._current_task_state is None:
            raise ValueError("No active task state to checkpoint")

        # Build current context for checkpoint
        context = self.build_context(
            goal=self._current_task_state.goal,
            current_step=self._current_task_state.current_step,
            task_state=self._current_task_state,
            conversation_history=self._conversation_history,
            provider=provider,
            model=model,
            budget=budget,
        )

        checkpoint = ContextCheckpoint(
            checkpoint_id=self._current_task_state.checkpoint_id,
            task_state=self._current_task_state,
            context_layers={lc.layer: lc for lc in context.layers},
            provider=provider or ProviderType.UNKNOWN,
            model=model,
            total_tokens=context.total_tokens,
            budget=context.budget,
            metadata=metadata or {},
        )

        self._checkpoints[checkpoint.checkpoint_id] = checkpoint
        logger.info(f"Created context checkpoint: {checkpoint.checkpoint_id}")
        return checkpoint

    def restore_checkpoint(self, checkpoint_id: str) -> Optional[ContextCheckpoint]:
        """Restore task state from checkpoint with schema validation."""
        checkpoint = self._checkpoints.get(checkpoint_id)
        if not checkpoint:
            logger.warning(f"Checkpoint not found: {checkpoint_id}")
            return None

        # Validate schema version
        schema_version = getattr(checkpoint, 'schema_version', 0)
        if schema_version != CONTEXT_SCHEMA_VERSION:
            logger.error(f"Checkpoint schema version mismatch: expected {CONTEXT_SCHEMA_VERSION}, got {schema_version}")
            return None

        # Validate checkpoint integrity
        if not self._validate_checkpoint(checkpoint):
            logger.error(f"Checkpoint validation failed: {checkpoint_id}")
            return None

        self._current_task_state = checkpoint.task_state
        logger.info(f"Restored context checkpoint: {checkpoint_id}")
        return checkpoint

    def _validate_checkpoint(self, checkpoint: ContextCheckpoint) -> bool:
        """Validate checkpoint integrity."""
        try:
            # Check required fields
            if not checkpoint.checkpoint_id:
                return False
            if not checkpoint.task_state:
                return False
            if not checkpoint.task_state.goal:
                return False
            if not checkpoint.task_state.checkpoint_id:
                return False
            if checkpoint.total_tokens < 0:
                return False
            if checkpoint.budget <= 0:
                return False
            # Validate provider
            if checkpoint.provider not in ProviderType:
                return False
            return True
        except Exception as e:
            logger.error(f"Checkpoint validation error: {e}")
            return False

    def list_checkpoints(self) -> List[Dict[str, Any]]:
        """List available checkpoints."""
        return [
            {
                "checkpoint_id": cp.checkpoint_id,
                "goal": cp.task_state.goal,
                "current_step": cp.task_state.current_step,
                "completed_steps": len(cp.task_state.completed_steps),
                "created_at": cp.created_at,
                "tokens": cp.total_tokens,
            }
            for cp in self._checkpoints.values()
        ]

    def delete_checkpoint(self, checkpoint_id: str) -> bool:
        """Delete a checkpoint."""
        if checkpoint_id in self._checkpoints:
            del self._checkpoints[checkpoint_id]
            return True
        return False

    # ------------------------------------------------------------------
    # Compression
    # ------------------------------------------------------------------

    def compress_context(self, context: BuiltContext, target_budget: int) -> BuiltContext:
        """Compress context to fit within target budget."""
        if context.total_tokens <= target_budget:
            return context

        if target_budget <= 0:
            logger.error(f"Invalid target budget: {target_budget}")
            target_budget = 512  # Minimum safe budget

        # Re-apply budget with lower limit
        compressed_layers = self.builder._apply_budget(context.layers, target_budget)

        return BuiltContext(
            layers=compressed_layers,
            total_tokens=sum(l.tokens for l in compressed_layers),
            budget=target_budget,
            provider=context.provider,
            model=context.model,
            truncated=True,
            truncation_details={
                **context.truncation_details,
                "compressed_from": context.total_tokens,
                "compressed_to": target_budget,
            },
        )

    def compact_conversation(self, keep_turns: int = 4) -> str:
        """Create a compact summary of conversation history."""
        if len(self._conversation_history) <= keep_turns:
            return ""

        old_turns = self._conversation_history[:-keep_turns]
        # Simple summarization: extract key topics
        topics = set()
        for turn in old_turns:
            content = turn.get("content", "").lower()
            # Extract potential topics (capitalized words, file paths, etc.)
            import re
            words = re.findall(r'\b[A-Z][a-z]+(?:\.[a-z]+)?\b', content)
            topics.update(words[:5])

        summary = f"[Previous conversation: {len(old_turns)} turns. Topics: {', '.join(list(topics)[:10])}]"
        return summary

    # ------------------------------------------------------------------
    # Failure Recovery
    # ------------------------------------------------------------------

    def recover_from_corrupted_context(self, context: BuiltContext) -> BuiltContext:
        """Attempt to recover from corrupted context by rebuilding with safe defaults."""
        logger.warning("Attempting context recovery from corruption")
        
        # If context is corrupted, rebuild with minimal safe context
        safe_layers = []
        for layer in context.layers:
            if layer.layer in (ContextLayer.SYSTEM, ContextLayer.CURRENT_TASK):
                safe_layers.append(layer)
        
        # Ensure we have at least SYSTEM layer
        if not any(l.layer == ContextLayer.SYSTEM for l in safe_layers):
            safe_layers.insert(0, LayerContent(
                layer=ContextLayer.SYSTEM,
                content="System: Safe mode - context recovered from corruption",
                tokens=20,
                priority=LAYER_PRIORITY[ContextLayer.SYSTEM],
                truncated=False,
            ))
        
        return BuiltContext(
            layers=safe_layers,
            total_tokens=sum(l.tokens for l in safe_layers),
            budget=context.budget,
            provider=context.provider,
            model=context.model,
            truncated=True,
            truncation_details={
                "recovered_from_corruption": True,
                "original_layers": len(context.layers),
                "recovered_layers": len(safe_layers),
            },
        )

    def recover_from_invalid_budget(self, budget: int) -> int:
        """Recover from invalid budget by clamping to valid range."""
        if budget <= 0:
            logger.warning(f"Invalid budget {budget}, using minimum safe budget")
            return 512
        if budget > 32768:
            logger.warning(f"Budget {budget} exceeds maximum, clamping to 32768")
            return 32768
        return budget

    def recover_from_unknown_provider(self, provider: ProviderType) -> Tuple[ProviderType, int]:
        """Recover from unknown provider by using safe defaults."""
        if provider == ProviderType.UNKNOWN:
            logger.warning("Unknown provider, using safe defaults (builtin)")
            return ProviderType.BUILTIN, DEFAULT_CONTEXT_BUDGETS[ProviderType.BUILTIN]
        return provider, DEFAULT_CONTEXT_BUDGETS.get(provider, 2048)

    def get_diagnostics_summary(self) -> Dict[str, Any]:
        """Get summary of context manager state for observability."""
        return {
            "active_task": self._current_task_state.goal if self._current_task_state else None,
            "task_step": self._current_task_state.current_step if self._current_task_state else None,
            "completed_steps": len(self._current_task_state.completed_steps) if self._current_task_state else 0,
            "checkpoints": len(self._checkpoints),
            "conversation_turns": len(self._conversation_history),
            "schema_version": CONTEXT_SCHEMA_VERSION,
        }


# ----------------------------------------------------------------------
# Factory
# ----------------------------------------------------------------------


def create_context_manager(
    memory_manager: MemoryManager,
    model_manager: ModelManager,
    default_budget: Optional[int] = None,
) -> ContextManager:
    """Factory function to create ContextManager."""
    return ContextManager(memory_manager, model_manager, default_budget)