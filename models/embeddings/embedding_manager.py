from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Embedding Manager
Author: Heeran Paul
License: MIT
--------------------------------------------

Single facade for embedding inference. Holds named providers keyed by
model id, routes ``create/batch`` (legacy) and ``embed/embed_batch``
to the selected provider, caches by (text hash, model id, version),
splits batches under resource pressure, and records latency/usage
stats. Only content hashes — never raw text — reach logs/traces.
"""

import logging
import time
from typing import Any, Dict, List, Optional

from models.embeddings.cache import EmbeddingCache
from models.embeddings.provider import (
    EmbeddingProvider,
    EmbeddingUnavailableError,
    text_fingerprint,
    validate_vector,
)

logger = logging.getLogger("HERCULE.Models.EmbeddingManager")


class EmbeddingManager:
    def __init__(
        self,
        client=None,
        providers: Optional[Dict[str, EmbeddingProvider]] = None,
        default_model: Optional[str] = None,
        cache: Optional[EmbeddingCache] = None,
        batch_size: int = 32,
        low_memory_batch_size: int = 8,
        resource_fn=None,
        routing_memory=None,
        use_cache: bool = True,
        tracer=None,
        timeout_s: Optional[float] = None,
    ):
        self.client = client
        self.providers: Dict[str, EmbeddingProvider] = dict(providers or {})
        if client is not None and "ollama-default" not in self.providers:
            from models.embeddings.ollama_provider import OllamaEmbeddingProvider

            self.providers.setdefault("ollama-default", OllamaEmbeddingProvider())
        self.default_model = default_model or (next(iter(self.providers), None))
        self.cache = cache or EmbeddingCache()
        self.batch_size = batch_size
        self.low_memory_batch_size = low_memory_batch_size
        self.resource_fn = resource_fn
        self.routing_memory = routing_memory
        self.use_cache = use_cache
        self.tracer = tracer
        self.timeout_s = timeout_s
        self.stats: Dict[str, Any] = {"requests": 0, "batch_requests": 0, "latency_ms": 0.0}

    def _run_provider_call(self, fn):
        """Run a provider call with the optional timeout enforced."""
        if not self.timeout_s:
            return fn()
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="hercule-embed") as pool:
            future = pool.submit(fn)
            try:
                return future.result(timeout=self.timeout_s)
            except concurrent.futures.TimeoutError:
                from models.embeddings.provider import EmbeddingError

                raise EmbeddingError(
                    f"embedding timed out after {self.timeout_s}s", "EMBEDDING_TIMEOUT"
                )

    def _trace(self, correlation_id: str, **entry) -> None:
        if not correlation_id or self.tracer is None:
            return
        try:
            from system.observability.trace import trace_embedding

            trace_embedding(self.tracer, correlation_id, **entry)
        except Exception:
            pass

    def _record_outcome(self, model_id: str, success: bool, latency_ms: float) -> None:
        if self.routing_memory is None:
            return
        try:
            record = getattr(self.routing_memory, "record", None)
            if callable(record):
                record(model_id, "embedding", success, latency_ms)
            else:
                record_embedding = getattr(self.routing_memory, "record_embedding_outcome", None)
                if callable(record_embedding):
                    record_embedding(model_id, success, latency_ms)
        except Exception:
            pass

    # --------------------------------------------------
    # provider selection
    # --------------------------------------------------
    def register_provider(self, provider: EmbeddingProvider) -> None:
        self.providers[provider.model_id] = provider
        if self.default_model is None:
            self.default_model = provider.model_id

    def available_models(self) -> List[str]:
        return [model_id for model_id, provider in self.providers.items() if provider.available()]

    def provider_for(self, model: Optional[str] = None) -> EmbeddingProvider:
        model_id = model or self.default_model
        provider = self.providers.get(model_id or "")
        if provider is None:
            raise EmbeddingUnavailableError(f"no embedding provider registered for model '{model_id}'")
        if not provider.available():
            raise EmbeddingUnavailableError(f"embedding provider '{model_id}' is unavailable")
        return provider

    def health(self) -> Dict[str, Any]:
        return {model_id: provider.health() for model_id, provider in self.providers.items()}

    # --------------------------------------------------
    # legacy API (backwards compatible)
    # --------------------------------------------------
    def create(self, model: str, text: str):
        return self.embed(text, model=model if model in self.providers else None)

    def batch(self, model: str, texts: list[str]):
        return self.embed_batch(texts, model=model if model in self.providers else None)

    # --------------------------------------------------
    # primary API
    # --------------------------------------------------
    def _effective_batch_size(self) -> int:
        if self.resource_fn is None:
            return self.batch_size
        try:
            snapshot = self.resource_fn() or {}
        except Exception:
            return self.batch_size
        if snapshot.get("source") != "psutil":
            return self.batch_size
        if float(snapshot.get("ram_percent", 0.0)) >= 90.0 or float(snapshot.get("cpu_percent", 0.0)) >= 90.0:
            return self.low_memory_batch_size
        return self.batch_size

    def embed(self, text: str, model: Optional[str] = None, correlation_id: str = "") -> List[float]:
        provider = self.provider_for(model)
        if self.use_cache:
            cached = self.cache.get(text, provider.model_id, provider.dimension)
            if cached is not None:
                self._trace(correlation_id, model_id=provider.model_id, dimension=len(cached),
                            batch_size=1, latency_ms=0.0, cache_hit=True,
                            fingerprints=[text_fingerprint(text)])
                return cached
        started = time.perf_counter()
        try:
            vector = validate_vector(
                self._run_provider_call(lambda: provider.embed(text)), provider.dimension, "manager-embed"
            )
        except Exception:
            self._record_outcome(provider.model_id, False, (time.perf_counter() - started) * 1000.0)
            raise
        latency_ms = (time.perf_counter() - started) * 1000.0
        self._record_outcome(provider.model_id, True, latency_ms)
        self.stats["requests"] += 1
        self.stats["latency_ms"] += latency_ms
        if self.use_cache:
            self.cache.put(text, provider.model_id, vector)
        self._trace(correlation_id, model_id=provider.model_id, dimension=len(vector),
                    batch_size=1, latency_ms=latency_ms, cache_hit=False,
                    fingerprints=[text_fingerprint(text)])
        logger.debug("embedded fp=%s model=%s dim=%d", text_fingerprint(text), provider.model_id, len(vector))
        return vector

    def embed_batch(self, texts: List[str], model: Optional[str] = None, correlation_id: str = "") -> List[List[float]]:
        provider = self.provider_for(model)
        vectors: List[Optional[List[float]]] = [None] * len(texts)
        pending: List[str] = []
        pending_idx: List[int] = []
        for i, text in enumerate(texts):
            if not self.use_cache:
                pending.append(text)
                pending_idx.append(i)
                continue
            cached = self.cache.get(text, provider.model_id, provider.dimension)
            if cached is not None:
                vectors[i] = cached
            else:
                pending.append(text)
                pending_idx.append(i)
        chunk = max(1, self._effective_batch_size())
        started = time.perf_counter()
        fresh: Dict[str, List[float]] = {}
        try:
            for start in range(0, len(pending), chunk):
                batch = pending[start : start + chunk]
                produced = self._run_provider_call(lambda batch=batch: provider.embed_batch(batch))
                if len(produced) != len(batch):
                    raise EmbeddingUnavailableError(
                        f"provider '{provider.model_id}' returned {len(produced)} vectors for {len(batch)} texts"
                    )
                for text, vector in zip(batch, produced):
                    validated = validate_vector(vector, provider.dimension, "manager-batch")
                    if self.use_cache:
                        self.cache.put(text, provider.model_id, validated)
                    fresh[text] = validated
        except Exception:
            self._record_outcome(provider.model_id, False, (time.perf_counter() - started) * 1000.0)
            raise
        if pending:
            latency_ms = (time.perf_counter() - started) * 1000.0
            self._record_outcome(provider.model_id, True, latency_ms)
            self.stats["batch_requests"] += 1
            self.stats["latency_ms"] += latency_ms
            self._trace(correlation_id, model_id=provider.model_id,
                        dimension=provider.dimension, batch_size=len(pending),
                        latency_ms=latency_ms, cache_hit=False,
                        fingerprints=[text_fingerprint(t) for t in pending[:5]])
        elif texts:
            self._trace(correlation_id, model_id=provider.model_id,
                        dimension=provider.dimension, batch_size=len(texts),
                        latency_ms=0.0, cache_hit=True,
                        fingerprints=[text_fingerprint(t) for t in texts[:5]])
        for text, i in zip(pending, pending_idx):
            vectors[i] = fresh[text]
        return [v for v in vectors if v is not None]

    def throughput_stats(self) -> Dict[str, Any]:
        total = self.stats["requests"] + self.stats["batch_requests"]
        return {
            **self.stats,
            "cache": self.cache.stats.as_dict(),
            "avg_latency_ms": round(self.stats["latency_ms"] / total, 3) if total else 0.0,
        }
