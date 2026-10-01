from __future__ import annotations
"""HERCULE PC-Frontier: Enhanced Model Router.

Intelligent routing between:
- HERCULE Native LM
- Ollama
- Builtin
- Transformers

Routes based on:
- Task complexity
- Model availability
- Context size
- Latency requirements
- Memory constraints
- Reasoning requirement
- Tool requirement
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Callable

from models.router.model_router import ModelRouter
from models.router.advanced_router import AdvancedModelRouter, RoutingDecision, ModelRoutingFailure
from models.registry.registry import ModelInfo, ModelRegistry
from system.hardware import (
    HardwareInventory, RuntimeProfile, get_hardware_inventory, 
    get_runtime_profile, get_profile_config, can_load_model,
    estimate_model_memory
)
from models.hercule_lm.verifiers import (
    verify_math, verify_json, verify_tool_call, verify_python_tests,
    verify_refusal, verify_citation, verify_verification
)

logger = logging.getLogger("HERCULE.Models.PCFrontierRouter")


class TaskType(str, Enum):
    """Task classification types matching the spec."""
    CHAT = "chat"
    REASONING = "reasoning"
    CODING = "coding"
    FILE_OPERATION = "file_operation"
    RESEARCH = "research"
    PLANNING = "planning"
    CALCULATION = "calculation"
    AUTOMATION = "automation"
    ARC = "arc"
    SYSTEM_TASK = "system_task"


class VerificationType(str, Enum):
    """Types of deterministic verification available."""
    MATH = "math"
    JSON = "json"
    TOOL_CALL = "tool_call"
    PYTHON_TESTS = "python_tests"
    REFUSAL = "refusal"
    CITATION = "citation"
    VERIFICATION = "verification"


@dataclass
class TaskClassification:
    """Result of task classification."""
    task_type: TaskType
    confidence: float
    requires_reasoning: bool = False
    requires_tools: bool = False
    requires_verification: List[VerificationType] = field(default_factory=list)
    estimated_complexity: float = 0.5  # 0-1
    suggested_context_tokens: int = 1024


@dataclass
class RoutingPolicy:
    """Routing policy configuration."""
    prefer_native_for_simple: bool = True
    prefer_external_for_complex: bool = True
    max_native_context: int = 2048
    verification_required: bool = True
    tool_first: bool = True
    offline_mode: bool = False


@dataclass
class ModelCandidate:
    """A model candidate for routing."""
    name: str
    provider: str
    adapter_name: str
    context_length: int
    capabilities: List[str]
    priority: int
    estimated_memory_mb: float
    estimated_latency_ms: float
    is_native: bool = False
    is_loaded: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


class TaskClassifier:
    """Enhanced task classifier with all 10 categories from spec."""
    
    TASK_PATTERNS = {
        TaskType.CHAT: [
            "hello", "hi", "hey", "thanks", "thank you", "who are you",
            "what can you do", "help", "how are you", "good morning",
            "good evening", "bye", "goodbye", "chat", "talk"
        ],
        TaskType.REASONING: [
            "reason", "think", "analyze", "logic", "deduce", "infer",
            "conclude", "evaluate", "assess", "compare", "contrast",
            "why", "how", "explain", "justify", "argument", "proof"
        ],
        TaskType.CODING: [
            "code", "program", "function", "class", "debug", "bug",
            "python", "javascript", "typescript", "java", "cpp", "c++",
            "rust", "go", "script", "algorithm", "implement", "refactor",
            "test", "unit test", "api", "endpoint", "database", "sql"
        ],
        TaskType.FILE_OPERATION: [
            "file", "read", "write", "edit", "create", "delete", "copy",
            "move", "rename", "list", "directory", "folder", "path",
            "open", "save", "load", "find", "search", "grep"
        ],
        TaskType.RESEARCH: [
            "research", "study", "investigate", "explore", "survey",
            "literature", "paper", "article", "source", "reference",
            "cite", "bibliography", "review", "compare", "analyze"
        ],
        TaskType.PLANNING: [
            "plan", "schedule", "roadmap", "timeline", "milestone",
            "strategy", "organize", "structure", "design", "architect",
            "steps", "phases", "release", "sprint", "project"
        ],
        TaskType.CALCULATION: [
            "calculate", "compute", "math", "arithmetic", "multiply",
            "divide", "add", "subtract", "sum", "product", "equation",
            "formula", "solve", "derivative", "integral", "matrix",
            "statistics", "probability", "percentage",
            "*", "/", "+", "-", "times", "divided",
        ],
        TaskType.AUTOMATION: [
            "automate", "script", "workflow", "pipeline", "batch",
            "cron", "schedule", "trigger", "monitor", "watch",
            "deploy", "build", "ci", "cd", "pipeline"
        ],
        TaskType.ARC: [
            "arc", "grid", "pattern", "transformation", "reasoning",
            "abstract", "visual", "puzzle", "kaggle", "agi"
        ],
        TaskType.SYSTEM_TASK: [
            "system", "config", "setting", "preference", "option",
            "diagnose", "health", "status", "info", "version",
            "update", "upgrade", "install", "uninstall", "log"
        ],
    }
    
    # Task types that typically need reasoning
    REASONING_TYPES = {
        TaskType.REASONING, TaskType.CODING, TaskType.RESEARCH,
        TaskType.PLANNING, TaskType.ARC
    }
    
    # Task types that typically need tools
    TOOL_TYPES = {
        TaskType.CODING, TaskType.FILE_OPERATION, TaskType.RESEARCH,
        TaskType.AUTOMATION, TaskType.SYSTEM_TASK, TaskType.ARC
    }
    
    # Verification types per task
    VERIFICATION_MAP = {
        TaskType.CALCULATION: [VerificationType.MATH],
        TaskType.CODING: [VerificationType.PYTHON_TESTS, VerificationType.JSON],
        TaskType.FILE_OPERATION: [VerificationType.JSON],
        TaskType.AUTOMATION: [VerificationType.TOOL_CALL],
        TaskType.ARC: [VerificationType.VERIFICATION],
        TaskType.REASONING: [VerificationType.VERIFICATION],
    }
    
    def classify(self, text: str) -> TaskClassification:
        """Classify a task into one of the 10 categories."""
        text_lower = text.lower()
        scores = {}
        
        for task_type, keywords in self.TASK_PATTERNS.items():
            score = 0
            for keyword in keywords:
                if keyword in text_lower:
                    score += 1
            scores[task_type] = score
        
        # Find best match
        if not scores or max(scores.values()) == 0:
            best = TaskType.CHAT
            confidence = 0.3
        else:
            best = max(scores, key=scores.get)
            max_score = scores[best]
            total = sum(scores.values())
            confidence = min(0.95, max_score / max(1, total) + 0.3)
        
        # Determine properties
        requires_reasoning = best in self.REASONING_TYPES
        requires_tools = best in self.TOOL_TYPES
        verification_types = self.VERIFICATION_MAP.get(best, [])
        
        # Estimate complexity based on task type and text length
        complexity_base = {
            TaskType.CHAT: 0.1,
            TaskType.CALCULATION: 0.2,
            TaskType.FILE_OPERATION: 0.3,
            TaskType.SYSTEM_TASK: 0.3,
            TaskType.CODING: 0.6,
            TaskType.RESEARCH: 0.7,
            TaskType.PLANNING: 0.7,
            TaskType.AUTOMATION: 0.8,
            TaskType.REASONING: 0.8,
            TaskType.ARC: 0.9,
        }
        estimated_complexity = complexity_base.get(best, 0.5)
        
        # Adjust for text length
        if len(text) > 500:
            estimated_complexity = min(1.0, estimated_complexity + 0.2)
        elif len(text) > 200:
            estimated_complexity = min(1.0, estimated_complexity + 0.1)
        
        # Suggest context tokens
        context_tokens = {
            TaskType.CHAT: 1024,
            TaskType.CALCULATION: 512,
            TaskType.FILE_OPERATION: 1024,
            TaskType.SYSTEM_TASK: 1024,
            TaskType.CODING: 4096,
            TaskType.RESEARCH: 4096,
            TaskType.PLANNING: 4096,
            TaskType.AUTOMATION: 4096,
            TaskType.REASONING: 4096,
            TaskType.ARC: 8192,
        }.get(best, 2048)
        
        return TaskClassification(
            task_type=best,
            confidence=confidence,
            requires_reasoning=requires_reasoning,
            requires_tools=requires_tools,
            requires_verification=verification_types,
            estimated_complexity=estimated_complexity,
            suggested_context_tokens=context_tokens,
        )


class PCFRouter:
    """PC-Frontier Router: Hardware-aware, task-aware, verification-first."""
    
    def __init__(
        self,
        base_router: Optional[ModelRouter] = None,
        advanced_router: Optional[AdvancedModelRouter] = None,
        policy: Optional[RoutingPolicy] = None,
        hardware_inventory: Optional[HardwareInventory] = None,
    ):
        self.base_router = base_router or ModelRouter()
        self.advanced_router = advanced_router
        self.policy = policy or RoutingPolicy()
        self.hardware = hardware_inventory or get_hardware_inventory()
        self.profile = get_runtime_profile()
        self.profile_config = get_profile_config(self.profile)
        self.classifier = TaskClassifier()
        
        # Tool-first: map of deterministic tools
        self.tools: Dict[str, Callable] = {}
        self.verifiers: Dict[VerificationType, Callable] = {
            VerificationType.MATH: verify_math,
            VerificationType.JSON: verify_json,
            VerificationType.TOOL_CALL: verify_tool_call,
            VerificationType.PYTHON_TESTS: verify_python_tests,
            VerificationType.REFUSAL: verify_refusal,
            VerificationType.CITATION: verify_citation,
            VerificationType.VERIFICATION: verify_verification,
        }
        
        # Performance tracking
        self.routing_history: List[Dict[str, Any]] = []
        
    def classify_task(self, text: str) -> TaskClassification:
        """Classify the task to determine routing strategy."""
        return self.classifier.classify(text)
    
    def get_candidates(self, task: TaskClassification) -> List[ModelCandidate]:
        """Get available model candidates filtered by hardware constraints."""
        candidates = []
        registry = getattr(self.base_router, 'registry', None)
        
        if registry:
            for info in registry.enabled():
                # Estimate model memory (rough heuristic)
                # In practice, this would come from model metadata
                estimated_params = self._estimate_params(info)
                estimated_mem = estimate_model_memory(
                    estimated_params, 
                    quantized=self.profile_config.get("use_quantization", False),
                    context_tokens=min(task.suggested_context_tokens, info.context_length)
                )
                
                # Check if model fits in memory
                if estimated_mem > self.profile_config["memory_limit_mb"]:
                    continue
                
                # Check if native model is preferred/required
                is_native = info.provider == "hercule-lm" or info.metadata.get("native", False)
                if self.profile_config["prefer_native_lm"] and not is_native:
                    # Still allow but lower priority
                    pass
                
                candidates.append(ModelCandidate(
                    name=info.name,
                    provider=info.provider,
                    adapter_name=info.adapter_name or info.provider,
                    context_length=info.context_length,
                    capabilities=info.capabilities,
                    priority=info.priority,
                    estimated_memory_mb=estimated_mem,
                    estimated_latency_ms=self._estimate_latency(info, task),
                    is_native=is_native,
                    metadata=dict(info.metadata),
                ))
        
        # Sort by priority (lower = higher priority)
        candidates.sort(key=lambda c: (c.priority, c.estimated_memory_mb))
        return candidates
    
    def _estimate_params(self, info: ModelInfo) -> int:
        """Estimate parameter count from model info."""
        name = info.name.lower()
        provider = info.provider.lower()
        
        # Check name patterns first
        if any(p in name for p in ["100m", "micro", "tiny", "small", "nano"]):
            return 100_000_000
        elif "1b" in name:
            return 1_000_000_000
        elif "7b" in name:
            return 7_000_000_000
        elif "13b" in name:
            return 13_000_000_000
        elif "30b" in name or "33b" in name:
            return 30_000_000_000
        elif "70b" in name:
            return 70_000_000_000
        
        # Provider-specific defaults
        if provider == "hercule-lm":
            return 100_000_000
        elif provider == "builtin":
            return 100_000_000  # Local GGUF typically small
        elif provider == "transformers":
            if "tiny" in name or "small" in name:
                return 100_000_000
            return 1_000_000_000
        elif provider == "ollama":
            if "llama3" in name or "phi" in name or "gemma" in name:
                return 7_000_000_000
            return 7_000_000_000
        elif provider == "mock":
            return 1_000_000  # Tiny mock model
        
        return 1_000_000_000
    
    def _estimate_latency(self, info: ModelInfo, task: TaskClassification) -> float:
        """Estimate latency in ms for a model on this task."""
        base_latency = {
            "hercule-lm": 50,   # Fast native
            "builtin": 100,     # GGUF
            "ollama": 500,      # Network + model
            "transformers": 1000,  # Heavy
        }.get(info.provider, 500)
        
        # Adjust for task complexity
        return base_latency * (1 + task.estimated_complexity)
    
    def should_use_tool(self, task: TaskClassification) -> bool:
        """Determine if a deterministic tool should be used instead of model."""
        if not self.policy.tool_first:
            return False
        
        # Calculation -> calculator
        if task.task_type == TaskType.CALCULATION:
            return True
        
        # File operations -> filesystem tools
        if task.task_type == TaskType.FILE_OPERATION:
            return True
        
        # Structured output -> JSON verifier
        if task.requires_verification and VerificationType.JSON in task.requires_verification:
            return True
        
        return False
    
    def get_tool_for_task(self, task: TaskClassification) -> Optional[str]:
        """Get the recommended tool for a task type."""
        tool_map = {
            TaskType.CALCULATION: "calculator",
            TaskType.FILE_OPERATION: "filesystem",
            TaskType.CODING: "code_executor",
            TaskType.RESEARCH: "web_search",
            TaskType.AUTOMATION: "shell",
            TaskType.SYSTEM_TASK: "system_info",
            TaskType.ARC: "arc_solver",
        }
        return tool_map.get(task.task_type)
    
    def route(
        self, 
        task_text: str,
        preferred_model: Optional[str] = None,
        force_provider: Optional[str] = None,
    ) -> RoutingDecision:
        """Main routing entry point."""
        start_time = time.perf_counter()
        
        # Classify task
        classification = self.classify_task(task_text)
        
        # Check for tool-first routing
        if self.should_use_tool(classification):
            tool_name = self.get_tool_for_task(classification)
            logger.info(f"Task '{task_text[:50]}' routed to tool: {tool_name}")
            # Return a special decision indicating tool use
            return RoutingDecision(
                model=f"tool:{tool_name}",
                adapter_name="tool",
                reason=f"Deterministic tool '{tool_name}' preferred for {classification.task_type.value}",
                task_type=classification.task_type.value,
                scores=[],
                fallback_chain=[f"tool:{tool_name}"],
                requirements={"tool_first": 1.0},
            )
        
        # Get candidates
        candidates = self.get_candidates(classification)
        
        if not candidates:
            raise ModelRoutingFailure("No models available within hardware constraints")
        
        # Filter by force_provider if specified
        if force_provider:
            candidates = [c for c in candidates if c.provider == force_provider]
            if not candidates:
                raise ModelRoutingFailure(f"No models available for provider: {force_provider}")
        
        # Apply routing logic based on classification
        selected = self._select_best_candidate(candidates, classification, preferred_model)
        
        # Build decision
        decision = RoutingDecision(
            model=selected.name,
            adapter_name=selected.adapter_name,
            reason=self._explain_selection(selected, classification, candidates),
            task_type=classification.task_type.value,
            scores=[
                type('Score', (), {
                    'adapter_name': c.adapter_name,
                    'model_name': c.name,
                    'total': 1.0 - (i * 0.1),
                    'factors': {'priority': c.priority, 'memory': c.estimated_memory_mb}
                })()
                for i, c in enumerate(candidates[:5])
            ],
            fallback_chain=[c.name for c in candidates],
            requirements={
                "reasoning": 1.0 if classification.requires_reasoning else 0.0,
                "tools": 1.0 if classification.requires_tools else 0.0,
                "verification": 1.0 if classification.requires_verification else 0.0,
            },
        )
        
        # Record routing for analytics
        self.routing_history.append({
            "timestamp": time.time(),
            "task": task_text[:100],
            "classification": classification.task_type.value,
            "selected": selected.name,
            "latency_ms": (time.perf_counter() - start_time) * 1000,
        })
        
        return decision
    
    def _select_best_candidate(
        self, 
        candidates: List[ModelCandidate], 
        classification: TaskClassification,
        preferred_model: Optional[str] = None,
    ) -> ModelCandidate:
        """Select the best candidate based on task and hardware."""
        
        # If preferred model specified and available
        if preferred_model:
            for c in candidates:
                if c.name == preferred_model:
                    return c
        
        # For simple tasks, prefer native LM if available
        if (classification.task_type in {TaskType.CHAT, TaskType.CALCULATION} 
            and self.policy.prefer_native_for_simple):
            for c in candidates:
                if c.is_native:
                    return c
        
        # For complex reasoning tasks, prefer external if available and allowed
        if (classification.requires_reasoning 
            and self.policy.prefer_external_for_complex
            and self.profile_config.get("allow_external_models", True)):
            for c in candidates:
                if not c.is_native and c.provider in {"ollama", "builtin"}:
                    return c
        
        # For coding, prefer models with coding capability
        if classification.task_type == TaskType.CODING:
            for c in candidates:
                if "coding" in c.capabilities or "code" in str(c.capabilities).lower():
                    return c
        
        # Default: first candidate (highest priority)
        return candidates[0]
    
    def _explain_selection(
        self, 
        selected: ModelCandidate, 
        classification: TaskClassification,
        candidates: List[ModelCandidate],
    ) -> str:
        """Generate human-readable explanation for routing decision."""
        reasons = []
        
        if selected.is_native:
            reasons.append("native LM (fast, local)")
        else:
            reasons.append(f"{selected.provider} ({selected.name})")
        
        if classification.task_type == TaskType.CHAT:
            reasons.append("simple conversation")
        elif classification.requires_reasoning:
            reasons.append("reasoning task")
        elif classification.requires_tools:
            reasons.append("tool-required task")
        
        if self.profile != RuntimeProfile.HIGH:
            reasons.append(f"profile={self.profile.value}")
        
        return f"Selected {selected.name}: {', '.join(reasons)}"
    
    def verify_output(
        self, 
        output: str, 
        verification_types: List[VerificationType],
        reference: Any = None,
    ) -> Dict[str, Any]:
        """Run deterministic verifiers on model output."""
        results = {}
        all_passed = True
        
        for vtype in verification_types:
            verifier = self.verifiers.get(vtype)
            if not verifier:
                results[vtype.value] = {"pass": False, "score": 0.0, "detail": "No verifier"}
                all_passed = False
                continue
            
            try:
                if vtype == VerificationType.MATH and reference is not None:
                    result = verifier(output, str(reference))
                elif vtype == VerificationType.JSON:
                    result = verifier(output)
                elif vtype == VerificationType.TOOL_CALL:
                    result = verifier(output)
                elif vtype == VerificationType.PYTHON_TESTS and reference is not None:
                    result = verifier(output, reference)
                elif vtype == VerificationType.VERIFICATION and reference is not None:
                    result = verifier(output, str(reference))
                else:
                    result = verifier(output)
                
                results[vtype.value] = result
                if not result.get("pass", False):
                    all_passed = False
            except Exception as e:
                results[vtype.value] = {"pass": False, "score": 0.0, "detail": f"Verifier error: {e}"}
                all_passed = False
        
        return {
            "all_passed": all_passed,
            "results": results,
        }
    
    def get_fallback_chain(self, classification: TaskClassification) -> List[str]:
        """Get the fallback chain for a task type."""
        chain = []
        
        # Primary: best match for task
        candidates = self.get_candidates(classification)
        chain.extend([c.name for c in candidates[:3]])
        
        # Fallback: native LM if not already in chain
        native_candidates = [c for c in candidates if c.is_native]
        for c in native_candidates:
            if c.name not in chain:
                chain.append(c.name)
        
        # Ultimate fallback: mock
        if "mock" not in chain:
            chain.append("mock")
        
        return chain
    
    def health_check(self) -> Dict[str, Any]:
        """Check health of all adapters."""
        health = {}
        for name, adapter in getattr(self.base_router, 'adapters', {}).items():
            try:
                health[name] = adapter.health() if hasattr(adapter, "health") else {"status": "unknown"}
            except Exception as e:
                health[name] = {"status": "error", "error": str(e)}
        return health
    
    def get_routing_stats(self) -> Dict[str, Any]:
        """Get routing statistics."""
        if not self.routing_history:
            return {"total": 0}
        
        by_type = {}
        by_model = {}
        total_latency = 0
        
        for entry in self.routing_history:
            t = entry["classification"]
            m = entry["selected"]
            by_type[t] = by_type.get(t, 0) + 1
            by_model[m] = by_model.get(m, 0) + 1
            total_latency += entry["latency_ms"]
        
        return {
            "total": len(self.routing_history),
            "by_task_type": by_type,
            "by_model": by_model,
            "avg_routing_latency_ms": total_latency / len(self.routing_history),
            "current_profile": self.profile.value,
        }


def create_pc_frontier_router(
    base_router: Optional[ModelRouter] = None,
    advanced_router: Optional[AdvancedModelRouter] = None,
    policy: Optional[RoutingPolicy] = None,
) -> PCFRouter:
    """Factory function to create PC-Frontier router."""
    return PCFRouter(
        base_router=base_router,
        advanced_router=advanced_router,
        policy=policy,
    )