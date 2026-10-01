from __future__ import annotations
"""HERCULE PC-Frontier: Enhanced Memory Manager with Retrieve-Rank-Compact-Inject Pipeline.

Adds:
- Layered retrieval with ranking
- Compaction for information density
- Checkpoint/resume support for long tasks
- Offline-first operation
"""

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Callable

from memory.memory_manager import MemoryManager, MemoryRecord
from models.router.pc_frontier_router import TaskClassification, TaskType
from cognition.context.enhanced_context_manager import (
    RankedMemoryItem, InformationDensityScorer, MemoryCompactor, CompactedMemory,
)
from cognition.context.context_manager import TokenCounter
from system.hardware import get_runtime_profile, get_profile_config

logger = logging.getLogger("HERCULE.Memory.Enhanced")


@dataclass
class RetrievalResult:
    """Result of a retrieval operation."""
    items: List[RankedMemoryItem]
    total_candidates: int
    retrieval_time_ms: float
    query: str
    memory_types: List[str]


@dataclass
class InjectedContext:
    """Context injected into model call."""
    compacted: CompactedMemory
    raw_items: List[RankedMemoryItem]
    injection_tokens: int
    source: str


class RetrievalRanker:
    """Rank retrieved memories by relevance and task alignment."""
    
    def __init__(self):
        self.task_type_weights = {
            TaskType.CHAT: {"episodic": 0.8, "semantic": 0.6, "procedural": 0.3, "long_term": 0.4},
            TaskType.REASONING: {"semantic": 1.0, "episodic": 0.7, "procedural": 0.5, "long_term": 0.6},
            TaskType.CODING: {"procedural": 1.0, "semantic": 0.8, "episodic": 0.5, "long_term": 0.4},
            TaskType.FILE_OPERATION: {"episodic": 0.9, "semantic": 0.6, "long_term": 0.7, "procedural": 0.5},
            TaskType.RESEARCH: {"semantic": 1.0, "episodic": 0.6, "long_term": 0.7, "procedural": 0.4},
            TaskType.PLANNING: {"semantic": 0.9, "procedural": 0.8, "episodic": 0.7, "long_term": 0.5},
            TaskType.CALCULATION: {"semantic": 0.5, "procedural": 0.6, "episodic": 0.3, "long_term": 0.4},
            TaskType.AUTOMATION: {"procedural": 1.0, "episodic": 0.8, "semantic": 0.6, "long_term": 0.5},
            TaskType.ARC: {"episodic": 0.9, "semantic": 0.8, "procedural": 0.7, "long_term": 0.4},
            TaskType.SYSTEM_TASK: {"long_term": 0.8, "semantic": 0.7, "episodic": 0.5, "procedural": 0.4},
        }
    
    def rank(
        self,
        items: List[RankedMemoryItem],
        task_type: TaskType,
        query: str,
    ) -> List[RankedMemoryItem]:
        """Rank items by task-specific relevance."""
        weights = self.task_type_weights.get(task_type, {})
        
        for item in items:
            type_weight = weights.get(item.memory_type, 0.5)
            # Combine: original score * type weight * (1 + recency bonus)
            recency = item.metadata.get("recency", 0.5)
            item.score = item.score * type_weight * (1 + recency * 0.2)
        
        items.sort(key=lambda x: x.score, reverse=True)
        return items


class EnhancedMemoryManager:
    """Enhanced Memory Manager with PC-Frontier pipeline."""
    
    def __init__(
        self,
        base_memory: MemoryManager,
        task_classification: Optional[TaskClassification] = None,
    ):
        self.base = base_memory
        self.task_classification = task_classification
        self.profile = get_runtime_profile()
        self.profile_config = get_profile_config(self.profile)
        
        # Pipeline components
        self.ranker = RetrievalRanker()
        self.density_scorer = InformationDensityScorer(
            TokenCounter()  # Will be set properly
        )
        self.compactor = MemoryCompactor(TokenCounter())
        
        # Checkpoint/resume
        self._task_checkpoints: Dict[str, Dict[str, Any]] = {}
        self._checkpoint_lock = __import__('threading').Lock()
        
        # Retrieval stats
        self.retrieval_stats = {
            "total_queries": 0,
            "total_candidates": 0,
            "avg_latency_ms": 0.0,
            "cache_hits": 0,
        }
    
    def set_token_counter(self, token_counter):
        """Set token counter for density scoring."""
        self.density_scorer.token_counter = token_counter
        self.compactor.token_counter = token_counter
    
    def retrieve_rank_compact_inject(
        self,
        query: str,
        task_type: Optional[TaskType] = None,
        memory_types: Optional[List[str]] = None,
        limit: int = 8,
        max_tokens: int = 1500,
    ) -> InjectedContext:
        """
        Full retrieve-rank-compact-inject pipeline.
        
        1. RETRIEVE: Get candidate memories from all stores
        2. RANK: Score by task relevance and recency
        3. COMPACT: Compress to high-density summary
        4. INJECT: Return formatted for context inclusion
        """
        start_time = time.perf_counter()
        task_type = task_type or (self.task_classification.task_type if self.task_classification else TaskType.CHAT)
        memory_types = memory_types or ["semantic", "episodic", "procedural", "long_term"]
        
        # 1. RETRIEVE
        all_items = []
        for mem_type in memory_types:
            try:
                records = self.base.store.search(query, memory_type=mem_type, limit=limit * 2)
                for record in records:
                    content = record.content[:500]
                    all_items.append(RankedMemoryItem(
                        content=content,
                        memory_type=mem_type,
                        score=0.5,  # Base score, will be re-ranked
                        metadata={
                            "source": record.source,
                            "timestamp": record.timestamp,
                            "importance": record.importance,
                            "recency": self._compute_recency(record.timestamp),
                        },
                    ))
            except Exception as e:
                logger.warning(f"Retrieval from {mem_type} failed: {e}")
        
        # Also check in-process memory
        try:
            hits = self.base.retrieve_relevant(query, memory_types=memory_types, limit=limit)
            for hit in hits:
                all_items.append(RankedMemoryItem(
                    content=hit.get("content", "")[:500],
                    memory_type=hit.get("memory_type", "unknown"),
                    score=hit.get("score", 0.5),
                    metadata=hit,
                ))
        except Exception:
            pass
        
        total_candidates = len(all_items)
        
        # 2. RANK
        ranked = self.ranker.rank(all_items, task_type, query)
        
        # 3. COMPACT
        compacted = self.compactor.compact(ranked[:limit], max_tokens)
        
        # 4. INJECT
        injected = InjectedContext(
            compacted=compacted,
            raw_items=ranked[:limit],
            injection_tokens=compacted.compacted_tokens,
            source=f"retrieve_rank_compact_inject:{task_type.value}",
        )
        
        # Update stats
        retrieval_time = (time.perf_counter() - start_time) * 1000
        self.retrieval_stats["total_queries"] += 1
        self.retrieval_stats["total_candidates"] += total_candidates
        self.retrieval_stats["avg_latency_ms"] = (
            (self.retrieval_stats["avg_latency_ms"] * (self.retrieval_stats["total_queries"] - 1) + retrieval_time)
            / self.retrieval_stats["total_queries"]
        )
        
        return injected
    
    def _compute_recency(self, timestamp: Optional[str]) -> float:
        """Compute recency score (0-1, 1 = most recent)."""
        if not timestamp:
            return 0.5
        try:
            from datetime import datetime
            ts = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            age_hours = (datetime.now(ts.tzinfo) - ts).total_seconds() / 3600
            # Exponential decay: 1.0 at 0h, 0.5 at ~24h, 0.1 at ~168h
            return max(0.01, min(1.0, 2 ** (-age_hours / 24)))
        except Exception:
            return 0.5
    
    # Checkpoint/Resume for long tasks
    def create_task_checkpoint(
        self,
        task_id: str,
        goal: str,
        completed_steps: List[str],
        verified_facts: List[str],
        artifacts: Dict[str, str],
        relevant_memories: List[str],
    ) -> str:
        """Create a memory checkpoint for task resume."""
        checkpoint_id = f"cp-{task_id}-{uuid.uuid4().hex[:8]}"
        
        checkpoint = {
            "checkpoint_id": checkpoint_id,
            "task_id": task_id,
            "goal": goal,
            "completed_steps": completed_steps,
            "verified_facts": verified_facts,
            "artifacts": artifacts,
            "relevant_memories": relevant_memories,
            "timestamp": time.time(),
            "memory_stats": self.base.memory_statistics(),
        }
        
        with self._checkpoint_lock:
            self._task_checkpoints[checkpoint_id] = checkpoint
            
            # Also persist to durable store
            try:
                self.base.store.put(MemoryRecord(
                    memory_type="episodic",
                    source="checkpoint",
                    content=f"Task checkpoint: {goal} - {len(completed_steps)} steps completed",
                    tags=["checkpoint", task_id],
                    importance=0.8,
                    metadata=checkpoint,
                ))
                self.base.store.save()
            except Exception as e:
                logger.warning(f"Checkpoint persist failed: {e}")
        
        return checkpoint_id
    
    def restore_task_checkpoint(self, checkpoint_id: str) -> Optional[Dict[str, Any]]:
        """Restore task state from checkpoint."""
        with self._checkpoint_lock:
            checkpoint = self._task_checkpoints.get(checkpoint_id)
            if not checkpoint:
                # Try durable store
                try:
                    records = self.base.store.search("checkpoint", memory_type="episodic", limit=10)
                    for record in records:
                        if record.metadata.get("checkpoint_id") == checkpoint_id:
                            checkpoint = record.metadata
                            break
                except Exception:
                    pass
        
        return checkpoint
    
    def list_task_checkpoints(self, task_id: str) -> List[Dict[str, Any]]:
        """List checkpoints for a task."""
        with self._checkpoint_lock:
            return [
                {
                    "checkpoint_id": cp["checkpoint_id"],
                    "goal": cp["goal"],
                    "completed_steps": len(cp["completed_steps"]),
                    "timestamp": cp["timestamp"],
                }
                for cp in self._task_checkpoints.values()
                if cp.get("task_id") == task_id
            ]
    
    # Offline-first support
    def is_offline_capable(self) -> bool:
        """Check if memory system works offline."""
        return True  # Local memory always works offline
    
    def get_offline_stats(self) -> Dict[str, Any]:
        """Get memory stats for offline mode."""
        return {
            "offline_capable": True,
            "in_process": self.base.health(),
            "durable": self.base.store.statistics() if hasattr(self.base.store, 'statistics') else {},
            "profile": self.profile.value,
        }
    
    # Delegate other methods to base
    def __getattr__(self, name):
        return getattr(self.base, name)
    
    def get_retrieval_stats(self) -> Dict[str, Any]:
        """Get retrieval pipeline statistics."""
        return dict(self.retrieval_stats)


def create_enhanced_memory_manager(
    base_memory: MemoryManager,
    task_classification: Optional[TaskClassification] = None,
) -> EnhancedMemoryManager:
    """Factory for enhanced memory manager."""
    return EnhancedMemoryManager(base_memory, task_classification)