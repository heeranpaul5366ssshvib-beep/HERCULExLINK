from __future__ import annotations
from system.guardian_patch import UniversalFallbackMixin
"""
--------------------------------------------
HERCULE AI Operating System
Module: Memory Manager
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


from memory.working.working_memory import WorkingMemory
from memory.short_term.short_term_memory import ShortTermMemory
from memory.long_term.long_term_memory import LongTermMemory
from memory.semantic.semantic_memory import SemanticMemory
from memory.episodic.episodic_memory import EpisodicMemory
from memory.procedural.procedural_memory import ProceduralMemory
from memory.vector.vector_manager import VectorMemory
from memory.retrieval.retrival_engine import RetrievalEngine
from memory.compression.compression_manager import CompressionManager
from memory.persistence import MemoryRecord, PersistentStore

import logging as _logging
import os as _os

_logger = _logging.getLogger("HERCULE.Memory.Manager")

# Events below this importance stay in-process only (Phase 8: no disk
# growth from trivial chatter; task outcomes and facts persist).
PERSIST_IMPORTANCE_FLOOR = 0.4

# Secret patterns are redacted before any durable write (Phase 16:
# memory must never become a credential store).
_SECRET_RES = None


def _secret_patterns():
    global _SECRET_RES
    if _SECRET_RES is None:
        import re as _re

        _SECRET_RES = [
            _re.compile(r"(?i)\b(password|passwd|pwd|api[_-]?key|secret|token|bearer)\b\s*[:=]\s*(\S+)"),
            _re.compile(r"(?i)\b(sk-[A-Za-z0-9_-]{8,})"),
            _re.compile(r"(?i)Bearer\s+([A-Za-z0-9._~+/=-]{8,})"),
        ]
    return _SECRET_RES


def redact_secrets(text: str) -> str:
    """Replace credential-looking values with [REDACTED] (deterministic)."""
    cleaned = str(text or "")
    for pattern in _secret_patterns():
        def _mask(match):
            label = ""
            try:
                if match.lastindex and len(match.groups()) > 1:
                    label = str(match.group(1))
            except Exception:
                label = ""
            return (label + " [REDACTED]") if label else "[REDACTED]"
        cleaned = pattern.sub(_mask, cleaned)
    return cleaned


def _default_store_path() -> str:
    from system.config.runtime_config import load_runtime_config
    from system.paths import resolve_data_path
    base = load_runtime_config().memory_dir
    if base:
        return str(__import__("pathlib").Path(base) / "hercule_memory.json")
    return resolve_data_path("data/memory/hercule_memory.json")


class MemoryManager(UniversalFallbackMixin):
    """
    ============================================
              HERCULE MEMORY MANAGER
    ============================================

    Central gateway to every memory subsystem.

    All modules communicate ONLY through this
    manager.

    Memory Systems
    --------------
    • Working Memory
    • Short-Term Memory
    • Long-Term Memory
    • Semantic Memory
    • Episodic Memory
    • Procedural Memory
    • Vector Memory
    • Retrieval Engine
    • Compression Manager

    Future
    ------
    • Knowledge Graph
    • Memory Ranking
    • Importance Scoring
    • Reflection
    • Reinforcement Learning
    • Memory Consolidation
    • Forgetting Algorithms
    • Dreaming / Replay
    • Multi-Agent Shared Memory
    """

    def __init__(self, store_path: str = ""):

        ##################################################
        # ACTIVE MEMORY SYSTEMS
        ##################################################

        self.working = WorkingMemory()

        self.short_term = ShortTermMemory()

        self.long_term = LongTermMemory()

        self.semantic = SemanticMemory()

        self.episodic = EpisodicMemory()

        self.procedural = ProceduralMemory()

        self.vector = VectorMemory()

        self.retrieval = RetrievalEngine()

        self.compression = CompressionManager()

        ##################################################
        # PERSISTENT STORE (Stage 5: survives restarts)
        ##################################################

        self.store = PersistentStore(store_path or _default_store_path())
        self._rehydrate_from_store()
        # v2: optional production embedder (None = lexical fallback) +
        # last-recall telemetry for the HUD (never fabricated).
        self._embedder = None
        self.last_recall = {"at": 0.0, "count": 0, "query": ""}

    @property
    def tasks(self):
        """Compatibility: accessed by brain.reason via orchestrator.memory.tasks.
        Returns None since MemoryManager doesn't manage tasks directly.
        Task management is handled by cognition.task_manager.TaskManager.
        """
        return None

    ##################################################
    # SESSION MEMORY
    ##################################################

    def remember(self, data):

        self.working.add(data)

        self.short_term.add(data)

    def latest(self):

        return self.working.latest()

    def history(self):

        return self.short_term.get()

    def clear_session(self):

        self.working.clear()

        self.short_term.clear()

    ##################################################
    # LONG TERM MEMORY
    ##################################################

    def store(
        self,
        key,
        value,
    ):

        self.long_term.store(
            key,
            value,
        )
        try:
            self.store.put(MemoryRecord(
                memory_type="long_term", source="system",
                content=f"{key} = {redact_secrets(str(value))[:500]}",
                tags=["kv", str(key)], importance=0.6,
                metadata={"key": str(key)}))
            self.store.save()
        except Exception as exc:
            _logger.warning("long_term persist failed: %s", exc)

    def retrieve(
        self,
        key,
    ):

        hit = self.long_term.retrieve(key)
        if hit is not None:
            return hit
        # Fall back to the durable store (post-restart path).
        try:
            for record in self.store.all("long_term"):
                if record.metadata.get("key") == str(key):
                    return record.content.split(" = ", 1)[1] if " = " in record.content else record.content
        except Exception:
            pass
        return None

    def delete(
        self,
        key,
    ):

        self.long_term.delete(
            key,
        )
        try:
            for record in self.store.all("long_term"):
                if record.metadata.get("key") == str(key):
                    self.store.delete(record.id)
            self.store.save()
        except Exception as exc:
            _logger.warning("long_term delete persist failed: %s", exc)

    ##################################################
    # SEMANTIC MEMORY (+ explicit user facts, persisted)
    ##################################################

    def learn(
        self,
        topic,
        information,
    ):

        self.semantic.learn(
            topic,
            information,
        )

    def recall(
        self,
        topic,
    ):

        return self.semantic.recall(
            topic,
        )

    def forget(
        self,
        topic,
    ):

        self.semantic.forget(
            topic,
        )

    def remember_fact(self, topic, information, importance: float = 0.8,
                      correlation_id: str = ""):
        """Store an explicitly user-directed fact (durable + in-process).

        Same-topic predecessors are superseded (invalidated, history
        kept) so retrieval prefers current valid information. Secrets
        are redacted before any write.
        """
        topic = str(topic or "").strip().lower()[:120] or "general"
        information = redact_secrets(str(information or "").strip())[:1000]
        if not information:
            raise ValueError("empty fact: nothing to remember")
        self.semantic.learn(topic, information)
        try:
            superseded = 0
            for record in self.store.all("semantic"):
                if ((record.metadata or {}).get("topic") == topic
                        and not (record.metadata or {}).get("invalidated")
                        and record.content != information):
                    record.metadata["invalidated"] = True
                    record.metadata["superseded_by"] = information[:120]
                    record.outcome = record.outcome or "SUPERSEDED"
                    superseded += 1
            record = self.store.put(MemoryRecord(
                memory_type="semantic", source="user", content=information,
                tags=["fact", topic], importance=importance,
                correlation_id=correlation_id, metadata={"topic": topic}))
            self.store.save()
            stored = record.as_dict()
            stored["superseded"] = superseded
            return stored
        except Exception as exc:
            _logger.warning("fact persist failed: %s", exc)
            return {"topic": topic, "content": information, "persisted": False}

    def recall_fact(self, topic):
        """Recall a fact by topic (in-process first, durable store fallback)."""
        hit = self.semantic.recall(str(topic or "").strip().lower())
        if hit is not None:
            return hit
        try:
            for record in self.store.all("semantic"):
                if ((record.metadata or {}).get("invalidated")
                        or record.metadata.get("topic") != str(topic or "").strip().lower()):
                    continue
                self.semantic.learn(record.metadata["topic"], record.content)
                return record.content
        except Exception:
            pass
        return None

    def forget_fact(self, topic):
        """Invalidate a user fact (history kept, never retrieved again).

        Returns True when a live fact was invalidated. Retrieval skips
        invalidated records, so corrected information always wins.
        """
        topic = str(topic or "").strip().lower()
        self.semantic.forget(topic)
        removed = False
        try:
            for record in self.store.all("semantic"):
                if ((record.metadata or {}).get("topic") == topic
                        and not (record.metadata or {}).get("invalidated")):
                    record.metadata["invalidated"] = True
                    record.outcome = record.outcome or "FORGOTTEN"
                    removed = True
            self.store.save()
        except Exception as exc:
            _logger.warning("fact delete persist failed: %s", exc)
        return removed

    def facts(self):
        """All explicitly remembered facts (topic -> information)."""
        try:
            out = {}
            for record in self.store.all("semantic"):
                if (record.metadata or {}).get("invalidated"):
                    continue
                topic = record.metadata.get("topic")
                if topic and topic not in out:
                    out[topic] = record.content
            for topic in self.semantic.topics():
                out.setdefault(topic, self.semantic.recall(topic))
            return out
        except Exception:
            return {t: self.semantic.recall(t) for t in self.semantic.topics()}

    ##################################################
    # EPISODIC MEMORY (+ durable task summaries)
    ##################################################

    @staticmethod
    def _event_summary(event) -> tuple[str, float]:
        """Concise summary + importance; never stores reasoning traces."""
        if isinstance(event, dict):
            if event.get("kind") == "conversation":
                prompt = redact_secrets(str(event.get("prompt", ""))[:200])
                return f"conversation: {prompt}", 0.3
            task_id = str(event.get("task_id", ""))
            status = str(event.get("status", "")).upper()
            importance = {"COMPLETED": 0.7, "FAILED": 0.6}.get(status, 0.5)
            goal = redact_secrets(str((event.get("metadata") or {}).get("goal", "")))[:200]
            if not goal:
                goal = redact_secrets(str(event.get("goal", "")))[:200]
            summary = f"task {task_id} {status}".strip()
            if goal:
                summary += f": {goal}"
            return summary, importance
        return redact_secrets(str(event)[:200]), 0.4

    def remember_event(
        self,
        event,
    ):

        self.episodic.remember(
            event,
        )
        try:
            summary, importance = self._event_summary(event)
            if importance < PERSIST_IMPORTANCE_FLOOR:
                return  # trivial chatter stays in-process only
            metadata = {}
            correlation_id = ""
            task_id = ""
            if isinstance(event, dict):
                task_id = str(event.get("task_id", ""))
                correlation_id = str((event.get("metadata") or {}).get("correlation_id", "")
                                     or event.get("correlation_id", ""))
                metadata = {"goal": str((event.get("metadata") or {}).get("goal", ""))[:200]}
            self.store.put(MemoryRecord(
                memory_type="episodic", source="task", content=summary,
                tags=["event"], importance=importance, task_id=task_id,
                correlation_id=correlation_id, metadata=metadata))
            self.store.save()
        except Exception as exc:
            _logger.warning("event persist failed: %s", exc)

    def latest_event(self):

        return self.episodic.latest()

    def event_history(self):

        return self.episodic.history()

    ##################################################
    # PROCEDURAL MEMORY
    ##################################################

    def learn_skill(
        self,
        skill,
        procedure,
    ):

        self.procedural.learn(
            skill,
            procedure,
        )
        try:
            self.store.put(MemoryRecord(
                memory_type="procedural", source="task",
                content=f"procedure {skill}: {redact_secrets(str(procedure))[:500]}",
                tags=["procedure", str(skill)], importance=0.7,
                metadata={"skill": str(skill)}))
            self.store.save()
        except Exception as exc:
            _logger.warning("skill persist failed: %s", exc)

    def execute_skill(
        self,
        skill,
    ):

        return self.procedural.execute(
            skill,
        )

    ##################################################
    # VECTOR MEMORY
    ##################################################

    def store_vector(
        self,
        key,
        embedding,
        metadata=None,
    ):
        # VectorMemory.add(text, vector, metadata) is the backing API.
        return self.vector.add(
            key,
            embedding,
            metadata,
        )

    def retrieve_vector(
        self,
        key,
    ):
        # VectorMemory is similarity-addressed; a stored record is found
        # by key across both backends (in-memory _storage and FAISS).
        for record in getattr(self.vector, "_storage", []) or []:
            if record.get("text") == key:
                return record
        backend = getattr(self.vector, "_backend", None)
        for record in getattr(backend, "records", []) or []:
            if record.get("text") == key:
                return record
        if isinstance(key, list) and backend is not None and hasattr(backend, "search"):
            try:
                results = self.vector.search(key, top_k=5)
                for entry in results or []:
                    if entry.get("text") == key:
                        return entry
            except Exception:
                pass
        return None

    ##################################################
    # RETRIEVAL
    ##################################################

    def register_source(
        self,
        name,
        source,
    ):

        self.retrieval.register_source(
            name,
            source,
        )

    def unregister_source(
        self,
        name,
    ):

        self.retrieval.unregister_source(
            name,
        )

    def search(
        self,
        query,
    ):

        return self.retrieval.search(
            query,
        )

    ##################################################
    # DURABLE MEMORY (Stage 5: persistence + retrieval)
    ##################################################

    def save(self):
        """Flush durable records to disk."""
        try:
            return bool(self.store.save())
        except Exception as exc:
            _logger.warning("memory save failed: %s", exc)
            return False

    def load(self):
        """Reload durable records from disk and rehydrate live systems."""
        try:
            loaded = self.store.load()
            self._rehydrate_from_store()
            return loaded
        except Exception as exc:
            _logger.warning("memory load failed: %s", exc)
            return 0

    def search_memory(self, query, memory_type: str = "", limit: int = 10):
        """Deterministic retrieval over durable records (summaries only)."""
        try:
            return self.store.search(query, memory_type=memory_type, limit=limit)
        except Exception as exc:
            _logger.warning("memory search failed: %s", exc)
            return []

    ##################################################
    # RELEVANCE-AWARE RETRIEVAL (v2: layered + evidence)
    ##################################################

    def attach_embedder(self, provider) -> bool:
        """Attach a production embedding provider for semantic recall.

        Test-only vectors never qualify (honest lexical fallback).
        Returns True when semantic recall is genuinely available.
        """
        try:
            if provider is None or bool(getattr(provider, "test_only", False)):
                self._embedder = None
                return False
            healthy = False
            if hasattr(provider, "health"):
                try:
                    healthy = bool((provider.health() or {}).get("available", False))
                except Exception:
                    healthy = False
            elif hasattr(provider, "available"):
                try:
                    probe = provider.available()
                    healthy = bool(probe.get("available", True)) if isinstance(probe, dict) else bool(probe)
                except Exception:
                    healthy = False
            if not healthy or not hasattr(provider, "embed"):
                self._embedder = None
                return False
            self._embedder = provider
            return True
        except Exception:
            self._embedder = None
            return False

    def _embed(self, text: str):
        provider = getattr(self, "_embedder", None)
        if provider is None:
            return None
        try:
            vector = provider.embed(text)
            if not isinstance(vector, (list, tuple)) or not vector:
                return None
            return [float(v) for v in vector]
        except Exception:
            return None

    def retrieve_relevant(self, query, memory_types=None, limit: int = 8,
                          task_id: str = "", correlation_id: str = "",
                          entities=None):
        """Layered relevance retrieval with evidence metadata.

        Order: exact metadata -> entity/reference -> semantic (only
        with a production embedder) -> lexical fallback. Records the
        recall for HUD status. Never raises (honest empty on failure).
        """
        import time as _time

        try:
            types = list(memory_types or ["semantic", "episodic",
                                          "procedural", "long_term"])
            records = []
            for memory_type in types:
                records.extend(r.as_dict() for r in self.store.all(memory_type))
            from memory.relevance import rank

            hits = rank(records, str(query or ""), limit=limit,
                        task_id=str(task_id or ""),
                        correlation_id=str(correlation_id or ""),
                        entities=list(entities or []),
                        embed=self._embed if getattr(self, "_embedder", None) is not None else None)
            self.last_recall = {"at": _time.time(), "count": len(hits),
                                "query": str(query or "")[:120]}
            return hits
        except Exception as exc:
            _logger.warning("relevant retrieval failed: %s", exc)
            return []

    def recent_events(self, limit: int = 5):
        """Most recent episodic events with provenance."""
        try:
            items = sorted(self.store.all("episodic"),
                           key=lambda r: r.timestamp or "", reverse=True)
            return [{"content": r.content, "timestamp": r.timestamp,
                     "task_id": r.task_id, "outcome": r.outcome,
                     "evidence": {"source": r.source, "id": r.id}}
                    for r in items[:max(1, limit)]
                    if not (r.metadata or {}).get("invalidated")]
        except Exception:
            return []

    def explicit_memories(self):
        """Live user-explicit facts (invalidated excluded)."""
        return self.facts()

    def memories_about(self, entity: str, limit: int = 8):
        """Memories referencing an entity name/path (provenance included)."""
        return self.retrieve_relevant(entity, limit=limit,
                                      entities=[entity])

    def memories_for_task(self, task_id: str, limit: int = 8):
        """Memories associated with one task id."""
        if not str(task_id or "").strip():
            return []
        try:
            matches = [r.as_dict() for r in self.store.all()
                       if r.task_id == str(task_id)
                       and not (r.metadata or {}).get("invalidated")]
            matches.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
            return [{"content": r["content"], "memory_type": r["memory_type"],
                     "timestamp": r["timestamp"],
                     "evidence": {"source": r["source"], "id": r["id"]}}
                    for r in matches[:max(1, limit)]]
        except Exception:
            return []

    def procedures_for(self, hint: str = "", limit: int = 5):
        """Durable procedures, optionally filtered by skill hint."""
        try:
            items = [r for r in self.store.all("procedural")
                     if not (r.metadata or {}).get("invalidated")]
            if hint:
                from memory.relevance import tokens_of

                wanted = tokens_of(hint)
                items = [r for r in items
                         if wanted & tokens_of(r.content + " " + str((r.metadata or {}).get("skill", "")))]
            items.sort(key=lambda r: (r.importance, r.timestamp or ""), reverse=True)
            return [{"skill": (r.metadata or {}).get("skill", ""),
                     "content": r.content, "importance": r.importance,
                     "evidence": {"source": r.source, "id": r.id}}
                    for r in items[:max(1, limit)]]
        except Exception:
            return []

    def history_snapshot(self, limit: int = 10):
        """Cross-type recent history (provenance included)."""
        try:
            items = sorted(
                (r for r in self.store.all()
                 if not (r.metadata or {}).get("invalidated")),
                key=lambda r: r.timestamp or "", reverse=True)
            return [{"memory_type": r.memory_type, "content": r.content,
                     "timestamp": r.timestamp,
                     "evidence": {"source": r.source, "id": r.id}}
                    for r in items[:max(1, limit)]]
        except Exception:
            return []

    def memory_statistics(self):
        stats = {"in_process": {}, "durable": {}}
        try:
            stats["in_process"] = self.health()
        except Exception:
            pass
        try:
            stats["durable"] = self.store.statistics()
        except Exception:
            pass
        return stats

    def _rehydrate_from_store(self):
        """Repopulate live semantic/long-term systems from durable records."""
        try:
            for record in self.store.all("semantic"):
                topic = (record.metadata or {}).get("topic")
                if topic and self.semantic.recall(topic) is None:
                    self.semantic.learn(topic, record.content)
            for record in self.store.all("long_term"):
                key = (record.metadata or {}).get("key")
                if key and not self.long_term.exists(key):
                    value = record.content.split(" = ", 1)[1] if " = " in record.content else record.content
                    self.long_term.store(key, value)
        except Exception as exc:
            _logger.warning("memory rehydrate failed: %s", exc)

    ##################################################
    # COMPRESSION
    ##################################################

    def compress(
        self,
        text,
    ):

        return self.compression.compress(
            text,
        )

    def decompress(
        self,
        text,
    ):

        return self.compression.decompress(
            text,
        )

    ##################################################
    # HEALTH
    ##################################################

    def health(self):

        return {

            "working": self.working.size(),

            "short_term": self.short_term.size(),

            "long_term": len(self.long_term.all()),

            "semantic": len(self.semantic.topics()),

            "episodic": len(self.episodic.history()),

            "procedural": len(self.procedural.skills()),

            "vector": len(self.vector.all()),

            "retrieval_sources": len(
                self.retrieval.sources()
            ),

            "compression": True,
        }

    ##################################################
    # RESET
    ##################################################

    def reset(self):

        self.clear_session()

        self.long_term.clear()

        self.semantic.clear()

        self.episodic.clear()

        self.procedural.clear()

        self.vector.clear()

    ##################################################
    # FUTURE PLACEHOLDERS
    ##################################################

    def consolidate(self, experiences=None):
        """Bounded consolidation of durable memory (v2, real).

        * repeated episodic task summaries (>=3 same goal, successful)
          -> one concise semantic summary (episodics kept)
        * repeated verified facts are already strengthened at write
          time (confidence max); this pass only reports counts
        Returns a receipt (never raises).
        """
        receipt: dict = {"promoted": 0, "procedures": 0, "scanned": 0}
        try:
            from collections import Counter

            episodics = [r for r in self.store.all("episodic")
                         if not (r.metadata or {}).get("invalidated")]
            receipt["scanned"] = len(episodics)
            goals = Counter(str((r.metadata or {}).get("goal", "") or r.content[:80])
                            for r in episodics)
            for goal, count in goals.items():
                if count < 3 or not goal:
                    continue
                marker = f"consolidated: {goal[:120]}"
                exists = any(marker in r.content for r in self.store.all("semantic"))
                if exists:
                    continue
                self.store.put(MemoryRecord(
                    memory_type="semantic", source="consolidation",
                    content=f"{marker} (seen {count}x, all recorded outcomes kept as episodes)",
                    tags=["consolidated"], importance=0.6,
                    metadata={"goal": goal[:200], "count": count}))
                receipt["promoted"] += 1
            receipt["procedures"] = self._promote_experiences(experiences or [])
            self.store.save()
        except Exception as exc:
            _logger.warning("consolidation failed: %s", exc)
            receipt["error"] = str(exc)[:160]
        return receipt

    def _promote_experiences(self, experiences) -> int:
        """Verified experience groups -> procedural skills (advisory only).

        A capability set seen succeeding >=2 times becomes a persisted
        procedure. Procedures never bypass validation at execution time.
        """
        try:
            from collections import Counter

            groups = Counter()
            lessons: dict = {}
            for exp in experiences or []:
                get = (lambda k, d="": exp.get(k, d)) if isinstance(exp, dict) \
                    else (lambda k, d="": getattr(exp, k, d))
                if str(get("outcome", "")).upper() not in ("SUCCESS", "RECOVERED"):
                    continue
                caps = tuple(sorted(str(c).upper() for c in (get("capabilities", []) or [])))
                if not caps:
                    continue
                groups[caps] += 1
                lessons.setdefault(caps, str(get("lesson", ""))[:300])
            promoted = 0
            for caps, count in groups.items():
                if count < 2:
                    continue
                skill = "workflow:" + "+".join(caps).lower()
                if skill in self.procedural.skills():
                    continue
                procedure = {"capabilities": list(caps),
                             "uses": count, "lesson": lessons.get(caps, ""),
                             "advisory": True}
                self.learn_skill(skill, procedure)
                promoted += 1
            return promoted
        except Exception as exc:
            _logger.warning("procedure promotion failed: %s", exc)
            return 0

    def promote_procedure(self, skill: str, steps) -> bool:
        """Persist one verified workflow as an advisory procedure."""
        try:
            if not str(skill or "").strip() or not steps:
                return False
            self.learn_skill(f"workflow:{str(skill).strip().lower()}",
                             {"steps": [str(s)[:200] for s in steps][:12],
                              "advisory": True})
            return True
        except Exception:
            return False

    def reflect(self):
        """Lightweight self-reflection: consolidation receipt (bounded)."""
        return self.consolidate()

    def rank_importance(self, query: str = "", limit: int = 10):
        """Top records by importance/confidence/recency (no query needed)."""
        try:
            hits = self.retrieve_relevant(query or "task memory fact",
                                          limit=max(1, limit))
            return sorted(hits, key=lambda h: (
                h["factors"]["importance"], h["score"]), reverse=True)
        except Exception:
            return []

    def forget_unused(self, before_importance: float = 0.2, limit: int = 50):
        """Prune trivial non-explicit records (explicit facts exempt)."""
        pruned = 0
        try:
            for record in list(self.store.all()):
                if pruned >= max(1, limit):
                    break
                if record.source == "user" and "fact" in [str(t).lower() for t in (record.tags or [])]:
                    continue
                if record.memory_type in ("semantic", "procedural") and record.source == "user":
                    continue
                if float(record.importance or 0.0) < before_importance:
                    if self.store.delete(record.id):
                        pruned += 1
            if pruned:
                self.store.save()
        except Exception as exc:
            _logger.warning("forget_unused failed: %s", exc)
        return pruned

    def replay(self):
        """
        Replay previous experiences
        for continual learning.

        Future implementation.
        """
        pass

    def backup(self):
        """
        Save all memories to disk.

        Future implementation.
        """
        pass

    def restore(self):
        """
        Restore memories from disk.

        Future implementation.
        """
        pass
