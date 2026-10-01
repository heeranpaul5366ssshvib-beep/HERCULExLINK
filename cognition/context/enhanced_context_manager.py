from __future__ import annotations
"""HERCULE PC-Frontier: Enhanced Context Manager with Information Density Optimization.

Builds on existing ContextManager to add:
- Retrieve → Rank → Compact → Inject pipeline
- Information density scoring
- Dynamic layer pruning based on relevance
- Task-aware context selection
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Callable

from cognition.context.context_manager import (
    ContextManager, ContextBuilder, BuiltContext, LayerContent,
    ContextLayer, ProviderType, StructuredTaskState, ContextCheckpoint,
    DEFAULT_CONTEXT_BUDGETS, LAYER_PRIORITY, LAYER_MAX_TOKENS,
    TokenCounter, ToolOutputNormalizer, ContextDiagnostics,
    create_context_manager,
)
from memory.memory_manager import MemoryManager
from models.router.pc_frontier_router import TaskClassification, TaskType
from system.hardware import get_runtime_profile, get_profile_config

logger = logging.getLogger("HERCULE.ContextManager.Enhanced")


@dataclass
class RankedMemoryItem:
    """A memory item with relevance ranking."""
    content: str
    memory_type: str
    score: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    tokens: int = 0
    density_score: float = 0.0


@dataclass
class CompactedMemory:
    """Compacted memory with high information density."""
    summary: str
    original_tokens: int
    compacted_tokens: int
    compression_ratio: float
    key_points: List[str] = field(default_factory=list)


class InformationDensityScorer:
    """Score information density of text content."""
    
    # High-value patterns (more informative per token)
    HIGH_VALUE_PATTERNS = [
        (r'(?:^|\s)(def|class|function|import|from)\b', 2.0),      # Code structures
        (r'(?:^|\s)(error|exception|failed|success)\b', 1.5),      # Outcomes
        (r'(?:^|\s)(path|file|directory|config)\b', 1.5),          # File ops
        (r'(?:^|\s)(step|goal|plan|verify)\b', 1.5),               # Task structure
        (r'\d+\.?\d*', 1.2),                                  # Numbers
        (r'[A-Z][a-z]+(?:[A-Z][a-z]+)+', 1.3),               # CamelCase identifiers
    ]
    
    # Low-value patterns (less informative per token)
    LOW_VALUE_PATTERNS = [
        (r'(?:^|\s)(the|a|an|is|are|was|were|be|been|being)\b', 0.3),
        (r'(?:^|\s)(and|or|but|so|because|however|therefore)\b', 0.4),
        (r'(?:^|\s)(i|you|we|they|he|she|it)\b', 0.4),
        (r'(?:^|\s)(this|that|these|those)\b', 0.4),
        (r'\s+', 0.1),  # Whitespace
    ]
    
    def __init__(self, token_counter: TokenCounter):
        self.token_counter = token_counter
    
    def score(self, text: str) -> float:
        """Calculate information density score (higher = more dense)."""
        if not text:
            return 0.0
        
        tokens = self.token_counter.count(text)
        if tokens == 0:
            return 0.0
        
        score = 1.0  # Base score
        
        import re
        for pattern, weight in self.HIGH_VALUE_PATTERNS:
            matches = len(re.findall(pattern, text, re.IGNORECASE))
            score += matches * weight
        
        for pattern, weight in self.LOW_VALUE_PATTERNS:
            matches = len(re.findall(pattern, text, re.IGNORECASE))
            score -= matches * (1.0 - weight)
        
        # Normalize by token count
        density = max(0.1, score / tokens * 100)
        return min(10.0, density)  # Cap at 10
    
    def rank_items(self, items: List[RankedMemoryItem]) -> List[RankedMemoryItem]:
        """Rank memory items by combined relevance and density."""
        for item in items:
            density = self.score(item.content)
            item.density_score = density
            # Combined score: relevance * density
            item.tokens = self.token_counter.count(item.content)
            item.metadata['density'] = density
            item.metadata['combined_score'] = item.score * density
        
        # Sort by combined score descending
        items.sort(key=lambda x: x.metadata.get('combined_score', 0), reverse=True)
        return items


class MemoryCompactor:
    """Compact memories to increase information density."""
    
    def __init__(self, token_counter: TokenCounter, target_ratio: float = 0.3):
        self.token_counter = token_counter
        self.target_ratio = target_ratio
    
    def compact(self, items: List[RankedMemoryItem], max_tokens: int) -> CompactedMemory:
        """Compact multiple memory items into dense summary."""
        if not items:
            return CompactedMemory(
                summary="",
                original_tokens=0,
                compacted_tokens=0,
                compression_ratio=0.0,
            )
        
        # Combine all content
        full_content = "\n".join(f"[{i.memory_type}] {i.content}" for i in items)
        original_tokens = self.token_counter.count(full_content)
        
        # Extract key points (first sentence of each, or high-density segments)
        key_points = []
        for item in items:
            sentences = item.content.split('. ')
            if sentences:
                # Take first sentence or most dense segment
                key_points.append(sentences[0][:200])
        
        # Create summary
        summary_parts = []
        summary_parts.append(f"Retrieved {len(items)} memories:")
        for i, (item, point) in enumerate(zip(items, key_points)):
            summary_parts.append(f"  {i+1}. [{item.memory_type} score={item.score:.2f}] {point}")
        
        summary = "\n".join(summary_parts)
        compacted_tokens = self.token_counter.count(summary)
        
        # If still too long, truncate
        if compacted_tokens > max_tokens:
            max_chars = max_tokens * 4
            summary = summary[:max_chars] + "..."
            compacted_tokens = self.token_counter.count(summary)
        
        ratio = compacted_tokens / max(1, original_tokens)
        
        return CompactedMemory(
            summary=summary,
            original_tokens=original_tokens,
            compacted_tokens=compacted_tokens,
            compression_ratio=ratio,
            key_points=key_points,
        )


class EnhancedContextBuilder(ContextBuilder):
    """Enhanced context builder with information density optimization."""
    
    def __init__(
        self,
        memory_manager: MemoryManager,
        model_manager: Any,
        token_counter: Optional[TokenCounter] = None,
        task_classification: Optional[TaskClassification] = None,
    ):
        super().__init__(memory_manager, model_manager, token_counter)
        self.task_classification = task_classification
        self.density_scorer = InformationDensityScorer(token_counter or TokenCounter())
        self.compactor = MemoryCompactor(token_counter or TokenCounter())
        self.profile = get_runtime_profile()
        self.profile_config = get_profile_config(self.profile)
    
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
        """Build context with density optimization."""
        start_time = time.perf_counter()
        
        # Determine budget from profile if not specified
        if budget is None:
            budget = self.profile_config.get("max_context_tokens", 
                DEFAULT_CONTEXT_BUDGETS.get(provider, 2048))
        
        self.tokens.set_provider(provider if isinstance(provider, ContextLayer) else provider)
        
        if isinstance(provider, str):
            # Convert string to ProviderType
            try:
                provider = ProviderType(provider)
            except ValueError:
                provider = ProviderType.UNKNOWN
        
        layers = []
        diagnostics = ContextDiagnostics() if enable_diagnostics else None
        
        if diagnostics:
            diagnostics.provider = provider.value
            diagnostics.model = model
            diagnostics.budget = budget
        
        # L0: System (always included)
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
        
        # L1: Current Task (always included for active tasks)
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
        
        # L3: Relevant Memory (DENSITY OPTIMIZED)
        memory_content = self._build_memory_layer_dense(goal, task_state, budget)
        if memory_content:
            layer = self._build_layer(
                ContextLayer.RELEVANT_MEMORY,
                memory_content,
                budget,
                LAYER_MAX_TOKENS[ContextLayer.RELEVANT_MEMORY],
            )
            layers.append(layer)
            if diagnostics:
                diagnostics.layers_included.append(ContextLayer.RELEVANT_MEMORY.value)
                diagnostics.memory_items_selected += 1
        
        # L4: Tool Results (normalized)
        tool_content = self._build_tool_results_layer(tool_results)
        if tool_content:
            layer = self._build_layer(
                ContextLayer.TOOL_RESULTS,
                tool_content,
                budget,
                LAYER_MAX_TOKENS[ContextLayer.TOOL_RESULTS],
            )
            layers.append(layer)
            if diagnostics:
                diagnostics.layers_included.append(ContextLayer.TOOL_RESULTS.value)
                diagnostics.tool_results_selected += 1
        
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
            if diagnostics:
                diagnostics.layers_included.append(ContextLayer.VERIFICATION_STATE.value)
        
        # L6: Conversation (compacted)
        conv_content = self._build_conversation_layer_dense(conversation_history, budget)
        if conv_content:
            layer = self._build_layer(
                ContextLayer.CONVERSATION,
                conv_content,
                budget,
                LAYER_MAX_TOKENS[ContextLayer.CONVERSATION],
            )
            layers.append(layer)
            if diagnostics:
                diagnostics.layers_included.append(ContextLayer.CONVERSATION.value)
                diagnostics.conversation_turns_selected = len(conversation_history or [])
        
        # Apply density-aware budget
        final_layers = self._apply_density_budget(layers, budget, diagnostics)
        
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
                "density_optimized": True,
            },
            diagnostics=diagnostics,
        )
    
    def _build_memory_layer_dense(
        self,
        goal: str,
        task_state: Optional[StructuredTaskState],
        budget: int,
    ) -> str:
        """Build memory layer with retrieve-rank-compact-inject."""
        try:
            # Retrieve
            entities = []
            if task_state:
                entities.extend(task_state.relevant_memory)
            
            hits = self.memory.retrieve_relevant(
                goal,
                limit=10,  # Retrieve more for ranking
                entities=entities,
            )
            
            if not hits:
                return ""
            
            # Convert to ranked items
            ranked_items = []
            for hit in hits:
                content = hit.get("content", "")
                if not content:
                    continue
                ranked_items.append(RankedMemoryItem(
                    content=content[:500],  # Limit individual item size
                    memory_type=hit.get("memory_type", "unknown"),
                    score=hit.get("score", 0.5),
                    metadata=hit,
                ))
            
            # Rank by relevance * density
            ranked_items = self.density_scorer.rank_items(ranked_items)
            
            # Determine token budget for memory layer
            memory_budget = min(
                LAYER_MAX_TOKENS[ContextLayer.RELEVANT_MEMORY],
                budget // 4,  # Max 25% of budget
            )
            
            # Compact top items
            compacted = self.compactor.compact(ranked_items[:5], memory_budget)
            
            return compacted.summary
            
        except Exception as e:
            logger.warning(f"Dense memory layer failed: {e}")
            # Fallback to original
            return self._build_memory_layer(goal, task_state)
    
    def _build_conversation_layer_dense(
        self,
        conversation_history: Optional[List[Dict[str, str]]],
        budget: int,
    ) -> str:
        """Build conversation layer with density-aware compaction."""
        if not conversation_history:
            return ""
        
        conv_budget = min(
            LAYER_MAX_TOKENS[ContextLayer.CONVERSATION],
            budget // 6,  # Max ~16% of budget
        )
        
        # For short conversations, keep as-is
        if len(conversation_history) <= 4:
            return self._build_conversation_layer(conversation_history)
        
        # For longer conversations, compact older turns
        recent = conversation_history[-4:]
        older = conversation_history[:-4]
        
        parts = []
        # Compact older turns
        if older:
            topics = set()
            for turn in older:
                content = turn.get("content", "").lower()
                import re
                words = re.findall(r'\b[A-Z][a-z]+(?:\.[a-z]+)?\b', content)
                topics.update(words[:3])
            if topics:
                parts.append(f"[... {len(older)} earlier turns. Topics: {', '.join(list(topics)[:8])}]")
        
        # Recent turns verbatim
        for turn in recent:
            role = turn.get("role", "user")
            content = turn.get("content", "")[:200]
            parts.append(f"{role}: {content}")
        
        result = "\n".join(parts)
        
        # Truncate if needed
        tokens = self.tokens.count(result)
        if tokens > conv_budget:
            max_chars = conv_budget * 4
            result = result[:max_chars] + "..."
        
        return result
    
    def _apply_density_budget(
        self,
        layers: List[LayerContent],
        budget: int,
        diagnostics: Optional[ContextDiagnostics] = None,
    ) -> List[LayerContent]:
        """Apply budget with density-aware prioritization."""
        # Score each layer by priority * average density
        scored_layers = []
        for layer in layers:
            density = 1.0
            if layer.metadata.get('density'):
                density = layer.metadata['density']
            elif layer.content:
                density = self.density_scorer.score(layer.content)
            
            effective_priority = layer.priority * density
            scored_layers.append((effective_priority, layer))
        
        # Sort by effective priority
        scored_layers.sort(key=lambda x: x[0], reverse=True)
        
        result = []
        used = 0
        
        for eff_priority, layer in scored_layers:
            if used + layer.tokens <= budget:
                result.append(layer)
                used += layer.tokens
            elif used < budget:
                remaining = budget - used
                if remaining > 50:
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


class EnhancedContextManager(ContextManager):
    """Enhanced Context Manager with PC-Frontier optimizations."""
    
    def __init__(
        self,
        memory_manager: MemoryManager,
        model_manager: Any,
        default_budget: Optional[int] = None,
    ):
        # Initialize base but override builder
        super().__init__(memory_manager, model_manager, default_budget)
        self.builder = EnhancedContextBuilder(memory_manager, model_manager)
        self._task_classification: Optional[TaskClassification] = None
    
    def set_task_classification(self, classification: TaskClassification):
        """Set task classification for context optimization."""
        self._task_classification = classification
        self.builder.task_classification = classification
    
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
        """Build context with task-aware optimization."""
        # Update builder with current classification
        if self._task_classification:
            self.builder.task_classification = self._task_classification
        
        return super().build_context(
            goal=goal,
            current_step=current_step,
            plan=plan,
            task_state=task_state,
            tool_results=tool_results,
            verification_state=verification_state,
            conversation_history=conversation_history,
            system_prompt=system_prompt,
            provider=provider,
            model=model,
            budget=budget,
        )
    
    def get_density_stats(self) -> Dict[str, Any]:
        """Get information density statistics."""
        return {
            "profile": self.profile.value,
            "max_context_tokens": self.profile_config.get("max_context_tokens"),
            "memory_layer_budget": LAYER_MAX_TOKENS[ContextLayer.RELEVANT_MEMORY],
            "conversation_layer_budget": LAYER_MAX_TOKENS[ContextLayer.CONVERSATION],
        }


def create_enhanced_context_manager(
    memory_manager: MemoryManager,
    model_manager: Any,
    default_budget: Optional[int] = None,
) -> EnhancedContextManager:
    """Factory for enhanced context manager."""
    return EnhancedContextManager(memory_manager, model_manager, default_budget)