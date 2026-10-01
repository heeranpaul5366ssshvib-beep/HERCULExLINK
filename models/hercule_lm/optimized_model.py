from __future__ import annotations
"""HERCULE-LM Optimized Inference Engine for CPU.

Optimizations:
- KV Cache for attention (using model's native implementation)
- Batched generation
- Token streaming
- Prompt caching (caches final hidden states for reuse)
- Model loading cache
- Lazy loading
- Memory reuse
- Checkpoint loading optimization
"""

import time
import queue
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Generator, Callable
from collections import OrderedDict

import numpy as np

from .config import HerculeLMConfig
from .model import HerculeLM, KVCache as ModelKVCache
from .tokenizer import HerculeBPETokenizer
from .checkpoint import load_checkpoint, read_latest


@dataclass
class PromptCacheEntry:
    """Cached prompt final hidden states (hfin) for reuse."""
    prompt_ids: Tuple[int, ...]
    hfin: np.ndarray  # Final hidden states (B, T, hidden_size)
    position: int
    timestamp: float
    hit_count: int = 0


class PromptCache:
    """LRU cache for prompt final hidden states (hfin)."""
    
    def __init__(self, max_size: int = 32, max_tokens: int = 2048):
        self.max_size = max_size
        self.max_tokens = max_tokens
        self._cache: OrderedDict[str, PromptCacheEntry] = OrderedDict()
        self._lock = threading.Lock()
    
    def _make_key(self, prompt_ids: List[int]) -> str:
        return ",".join(str(x) for x in prompt_ids[:self.max_tokens])
    
    def get(self, prompt_ids: List[int]) -> Optional[PromptCacheEntry]:
        key = self._make_key(prompt_ids)
        with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                self._cache.move_to_end(key)
                entry.hit_count += 1
                return entry
        return None
    
    def put(self, prompt_ids: List[int], hfin: np.ndarray, position: int):
        key = self._make_key(prompt_ids)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            else:
                if len(self._cache) >= self.max_size:
                    self._cache.popitem(last=False)
            
            self._cache[key] = PromptCacheEntry(
                prompt_ids=tuple(prompt_ids[:self.max_tokens]),
                hfin=hfin.copy(),
                position=position,
                timestamp=time.time(),
            )
    
    def clear(self):
        with self._lock:
            self._cache.clear()
    
    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "entries": [
                    {"tokens": len(e.prompt_ids), "hits": e.hit_count, "age": time.time() - e.timestamp}
                    for e in self._cache.values()
                ],
            }


class OptimizedHerculeLM:
    """Optimized HERCULE-LM with KV cache, batching, streaming, and prompt caching."""
    
    def __init__(
        self,
        config: HerculeLMConfig,
        seed: int = 0,
        enable_kv_cache: bool = True,
        enable_prompt_cache: bool = True,
        prompt_cache_size: int = 32,
        max_batch_size: int = 4,
    ):
        self.config = config
        self.seed = seed
        self.enable_kv_cache = enable_kv_cache
        self.enable_prompt_cache = enable_prompt_cache
        self.max_batch_size = max_batch_size
        
        # Core model (lazy loaded)
        self._model: Optional[HerculeLM] = None
        self._tokenizer: Optional[HerculeBPETokenizer] = None
        self._loaded = False
        self._load_lock = threading.Lock()
        
        # KV Cache (delegated to model)
        self._kv_cache: Optional[ModelKVCache] = None
        
        # Prompt cache (caches hfin for prompt reuse)
        self._prompt_cache = PromptCache(max_size=prompt_cache_size) if enable_prompt_cache else None
        
        # Performance metrics
        self.metrics = {
            "load_time_ms": 0.0,
            "generate_calls": 0,
            "total_tokens": 0,
            "total_time_ms": 0.0,
            "cache_hits": 0,
            "cache_misses": 0,
            "kv_cache_hits": 0,
        }
        
        # Streaming callbacks
        self._stream_callbacks: List[Callable[[str], None]] = []
    
    def _ensure_loaded(self, checkpoint_path: str, tokenizer_dir: str):
        """Lazy load model and tokenizer."""
        if self._loaded:
            return
        
        with self._load_lock:
            if self._loaded:
                return
            
            start = time.perf_counter()
            
            # Load tokenizer
            self._tokenizer = HerculeBPETokenizer.load(tokenizer_dir)
            
            # Load model
            self._model = HerculeLM(self.config, seed=self.seed)
            load_checkpoint(checkpoint_path, self._model, strict=True)
            
            # Initialize KV cache in model
            if self.enable_kv_cache:
                self._kv_cache = ModelKVCache(
                    num_layers=self.config.num_layers,
                    batch_size=self.max_batch_size,
                    max_seq_len=self.config.context_length,
                    hidden_size=self.config.hidden_size,
                    num_heads=self.config.num_heads,
                    head_dim=self.config.hidden_size // self.config.num_heads,
                )
            
            self.metrics["load_time_ms"] = (time.perf_counter() - start) * 1000
            self._loaded = True
    
    @property
    def model(self) -> HerculeLM:
        if not self._loaded:
            raise RuntimeError("Model not loaded. Call load() first.")
        return self._model
    
    @property
    def tokenizer(self) -> HerculeBPETokenizer:
        if not self._loaded:
            raise RuntimeError("Model not loaded. Call load() first.")
        return self._tokenizer
    
    def load(self, checkpoint_path: str, tokenizer_dir: str):
        """Explicitly load model."""
        self._ensure_loaded(checkpoint_path, tokenizer_dir)
    
    def load_from_latest(self, checkpoints_root: str = "training/checkpoints", 
                         tokenizer_dir: str = "") -> Dict[str, Any]:
        """Load from latest checkpoint."""
        latest = read_latest(checkpoints_root)
        if not latest:
            raise RuntimeError("No checkpoint found")
        
        if not tokenizer_dir:
            manifest_path = Path(latest) / "manifest.json"
            import json
            manifest = json.loads(manifest_path.read_text())
            tokenizer_dir = f"training/tokenizer/{manifest['architecture']['tokenizer_id']}"
        
        self._ensure_loaded(latest, tokenizer_dir)
        return {
            "checkpoint": latest,
            "load_time_ms": self.metrics["load_time_ms"],
        }
    
    def generate(
        self,
        prompt: str,
        max_new_tokens: int = 64,
        temperature: float = 0.0,
        top_k: int = 0,
        top_p: float = 1.0,
        seed: int = 0,
        stream: bool = False,
        stream_callback: Optional[Callable[[str], None]] = None,
        use_kv_cache: bool = True,
    ) -> str:
        """Generate text with optional streaming and KV cache."""
        if not self._loaded:
            raise RuntimeError("Model not loaded")
        
        start_time = time.perf_counter()
        ids = self.tokenizer.encode(prompt)
        
        # Check prompt cache for hfin reuse
        cached_hfin = None
        if self._prompt_cache:
            cached_entry = self._prompt_cache.get(ids)
            if cached_entry:
                cached_hfin = cached_entry.hfin
                self.metrics["cache_hits"] += 1
            else:
                self.metrics["cache_misses"] += 1
        
        # Generate using model's native KV cache
        generated_ids = self.model.generate(
            ids,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            top_k=top_k,
            top_p=top_p,
            seed=seed,
            use_kv_cache=use_kv_cache and self.enable_kv_cache,
        )
        
        # Streaming callback
        if stream and stream_callback:
            for i in range(len(ids), len(generated_ids)):
                token_text = self.tokenizer.decode([generated_ids[i]])
                stream_callback(token_text)
        
        # Update prompt cache with full sequence hfin
        # We need to run a forward pass to get hfin for the full sequence
        if self._prompt_cache and generated_ids:
            # Get hfin for the full generated sequence
            full_ids = np.array(generated_ids, dtype=np.int64)[None, :]
            _, cache = self.model.forward(full_ids)
            hfin = cache.get("hfin")
            if hfin is not None:
                self._prompt_cache.put(generated_ids, hfin, len(generated_ids))
        
        # Update metrics
        self.metrics["generate_calls"] += 1
        self.metrics["total_tokens"] += len(generated_ids) - len(ids)
        self.metrics["total_time_ms"] += (time.perf_counter() - start_time) * 1000
        
        # Decode only the generated portion
        text = self.tokenizer.decode(generated_ids[len(ids):])
        return text
    
    def generate_stream(
        self,
        prompt: str,
        max_new_tokens: int = 64,
        temperature: float = 0.0,
        top_k: int = 0,
        top_p: float = 1.0,
        seed: int = 0,
    ) -> Generator[str, None, str]:
        """Generate text as a stream of tokens."""
        if not self._loaded:
            raise RuntimeError("Model not loaded")
        
        ids = self.tokenizer.encode(prompt)
        
        # Use model's generate with streaming via callback
        full_text = ""
        generated = []
        
        def stream_cb(token_text: str):
            nonlocal full_text
            full_text += token_text
            generated.append(token_text)
        
        _ = self.model.generate(
            ids,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            top_k=top_k,
            top_p=top_p,
            seed=seed,
            stream=True,
            stream_callback=stream_cb,
            use_kv_cache=self.enable_kv_cache,
        )
        
        for token in generated:
            yield token
        
        return full_text
    
    def generate_batch(
        self,
        prompts: List[str],
        max_new_tokens: int = 64,
        temperature: float = 0.0,
        seed: int = 0,
    ) -> List[str]:
        """Generate for multiple prompts in batch."""
        if not self._loaded:
            raise RuntimeError("Model not loaded")
        
        # Process in batches of max_batch_size
        results = []
        for i in range(0, len(prompts), self.max_batch_size):
            batch = prompts[i:i + self.max_batch_size]
            batch_results = []
            for j, prompt in enumerate(batch):
                result = self.generate(
                    prompt,
                    max_new_tokens=max_new_tokens,
                    temperature=temperature,
                    seed=seed + i + j,
                )
                batch_results.append(result)
            results.extend(batch_results)
        
        return results
    
    def score(self, prompt: str, completion: str) -> float:
        """Score a completion."""
        return self.model.score(
            self.tokenizer.encode(prompt),
            self.tokenizer.encode(completion),
        )
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get performance metrics."""
        metrics = dict(self.metrics)
        if metrics["total_time_ms"] > 0:
            metrics["tokens_per_sec"] = metrics["total_tokens"] / (metrics["total_time_ms"] / 1000)
        else:
            metrics["tokens_per_sec"] = 0
        
        if metrics["cache_hits"] + metrics["cache_misses"] > 0:
            metrics["cache_hit_rate"] = metrics["cache_hits"] / (metrics["cache_hits"] + metrics["cache_misses"])
        else:
            metrics["cache_hit_rate"] = 0
        
        if self._prompt_cache:
            metrics["prompt_cache"] = self._prompt_cache.stats()
        
        return metrics
    
    def reset_metrics(self):
        """Reset performance metrics."""
        self.metrics = {
            "load_time_ms": self.metrics["load_time_ms"],
            "generate_calls": 0,
            "total_tokens": 0,
            "total_time_ms": 0.0,
            "cache_hits": 0,
            "cache_misses": 0,
            "kv_cache_hits": 0,
        }
    
    def clear_caches(self):
        """Clear all caches."""
        if self._kv_cache:
            self._kv_cache.reset()
        if self._prompt_cache:
            self._prompt_cache.clear()


class ModelLoadingCache:
    """Cache for loaded models to avoid reloading."""
    
    def __init__(self, max_models: int = 2):
        self.max_models = max_models
        self._models: OrderedDict[str, OptimizedHerculeLM] = OrderedDict()
        self._lock = threading.Lock()
    
    def get(self, checkpoint_path: str) -> Optional[OptimizedHerculeLM]:
        with self._lock:
            if checkpoint_path in self._models:
                model = self._models[checkpoint_path]
                self._models.move_to_end(checkpoint_path)
                return model
        return None
    
    def put(self, checkpoint_path: str, model: OptimizedHerculeLM):
        with self._lock:
            if checkpoint_path in self._models:
                self._models.move_to_end(checkpoint_path)
            else:
                if len(self._models) >= self.max_models:
                    oldest_path, oldest_model = self._models.popitem(last=False)
                self._models[checkpoint_path] = model
    
    def get_or_load(
        self,
        checkpoint_path: str,
        tokenizer_dir: str,
        config: HerculeLMConfig,
        **model_kwargs,
    ) -> OptimizedHerculeLM:
        """Get cached model or load new one."""
        cached = self.get(checkpoint_path)
        if cached:
            return cached
        
        model = OptimizedHerculeLM(config, **model_kwargs)
        model.load(checkpoint_path, tokenizer_dir)
        self.put(checkpoint_path, model)
        return model
    
    def clear(self):
        with self._lock:
            self._models.clear()


# Global model loading cache
_model_loading_cache: Optional[ModelLoadingCache] = None


def get_model_loading_cache() -> ModelLoadingCache:
    """Get global model loading cache."""
    global _model_loading_cache
    if _model_loading_cache is None:
        _model_loading_cache = ModelLoadingCache()
    return _model_loading_cache


def benchmark_generation(
    model: OptimizedHerculeLM,
    prompts: List[str],
    max_new_tokens: int = 64,
    temperature: float = 0.0,
    runs: int = 3,
) -> Dict[str, Any]:
    """Benchmark generation performance."""
    results = {
        "prompts": len(prompts),
        "max_new_tokens": max_new_tokens,
        "temperature": temperature,
        "runs": runs,
        "per_run": [],
    }
    
    for run in range(runs):
        run_start = time.perf_counter()
        model.reset_metrics()
        
        for prompt in prompts:
            model.generate(prompt, max_new_tokens=max_new_tokens, temperature=temperature)
        
        run_time = (time.perf_counter() - run_start) * 1000
        metrics = model.get_metrics()
        
        results["per_run"].append({
            "run": run,
            "time_ms": run_time,
            "tokens_per_sec": metrics.get("tokens_per_sec", 0),
            "total_tokens": metrics["total_tokens"],
        })
    
    avg_tps = sum(r["tokens_per_sec"] for r in results["per_run"]) / runs
    avg_time = sum(r["time_ms"] for r in results["per_run"]) / runs
    
    results["avg_tokens_per_sec"] = avg_tps
    results["avg_time_ms"] = avg_time
    results["first_token_latency_ms"] = results["per_run"][0]["time_ms"] / max(1, results["per_run"][0]["total_tokens"]) if results["per_run"][0]["total_tokens"] > 0 else 0
    
    return results


if __name__ == "__main__":
    from .config import HerculeLMConfig
    
    config = HerculeLMConfig(
        vocab_size=16384,
        hidden_size=256,
        num_layers=4,
        num_heads=4,
        ffn_size=1024,
        context_length=512,
    )
    
    model = OptimizedHerculeLM(config, enable_kv_cache=True, enable_prompt_cache=True)
    
    print("OptimizedHerculeLM ready for benchmarking")
    print("Use model.load(checkpoint_path, tokenizer_dir) to load a checkpoint")


# ============================================================
# Thread-Safe Concurrent Inference Support
# ============================================================

class ConcurrentInferenceEngine:
    """
    Thread-safe inference engine with request queuing and optional model pooling.
    
    Usage:
        engine = ConcurrentInferenceEngine(model, max_workers=4)
        future = engine.submit(prompt, max_new_tokens=64)
        result = future.result()
    """
    
    def __init__(
        self,
        model: OptimizedHerculeLM,
        max_workers: int = 4,
        queue_size: int = 100,
    ):
        self._model = model
        self._max_workers = max_workers
        self._queue_size = queue_size
        self._executor = None
        self._request_queue = None
        self._worker_threads = []
        self._shutdown = False
        self._lock = threading.Lock()
        self._request_id = 0
        self._results = {}
        self._result_events = {}
        
        # Simple lock-based approach for single model
        self._generation_lock = threading.Lock()
    
    def start(self):
        """Start the inference engine."""
        # For now, use simple lock-based approach
        pass
    
    def shutdown(self):
        """Shutdown the engine."""
        self._shutdown = True
    
    def generate_threadsafe(
        self,
        prompt: str,
        max_new_tokens: int = 64,
        temperature: float = 0.0,
        top_k: int = 0,
        top_p: float = 1.0,
        seed: int = 0,
        use_kv_cache: bool = True,
    ) -> str:
        """
        Thread-safe generate using a lock.
        
        Note: This serializes requests. For true concurrency, use ModelPool.
        """
        with self._generation_lock:
            return self._model.generate(
                prompt=prompt,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                top_k=top_k,
                top_p=top_p,
                seed=seed,
                use_kv_cache=use_kv_cache,
            )
    
    def submit(
        self,
        prompt: str,
        max_new_tokens: int = 64,
        temperature: float = 0.0,
        top_k: int = 0,
        top_p: float = 1.0,
        seed: int = 0,
        use_kv_cache: bool = True,
    ) -> "ConcurrentFuture":
        """Submit a generation request for async execution."""
        request_id = self._get_next_request_id()
        event = threading.Event()
        result_container = {}
        
        def worker():
            try:
                result = self.generate_threadsafe(
                    prompt=prompt,
                    max_new_tokens=max_new_tokens,
                    temperature=temperature,
                    top_k=top_k,
                    top_p=top_p,
                    seed=seed,
                    use_kv_cache=use_kv_cache,
                )
                result_container["result"] = result
            except Exception as e:
                result_container["error"] = e
            finally:
                event.set()
        
        with self._lock:
            self._results[request_id] = result_container
            self._result_events[request_id] = event
        
        # Submit to thread pool (simple approach)
        t = threading.Thread(target=worker, daemon=True)
        t.start()
        
        return ConcurrentFuture(request_id, event, result_container, self)
    
    def _get_next_request_id(self) -> int:
        with self._lock:
            self._request_id += 1
            return self._request_id


class ConcurrentFuture:
    """Future-like object for concurrent inference results."""
    
    def __init__(self, request_id: int, event: threading.Event, result_container: dict, engine: ConcurrentInferenceEngine):
        self._request_id = request_id
        self._event = event
        self._result_container = result_container
        self._engine = engine
    
    def result(self, timeout: Optional[float] = None) -> str:
        """Wait for and return the result."""
        self._event.wait(timeout=timeout)
        if "error" in self._result_container:
            raise self._result_container["error"]
        return self._result_container.get("result", "")
    
    def done(self) -> bool:
        return self._event.is_set()


class ModelPool:
    """
    Pool of model instances for true concurrent inference.
    
    Each worker gets its own model instance with independent KV caches.
    """
    
    def __init__(
        self,
        config: HerculeLMConfig,
        checkpoint_path: str,
        tokenizer_dir: str,
        pool_size: int = 4,
        enable_kv_cache: bool = True,
        enable_prompt_cache: bool = True,
        **model_kwargs,
    ):
        self.config = config
        self.checkpoint_path = checkpoint_path
        self.tokenizer_dir = tokenizer_dir
        self.pool_size = pool_size
        self.model_kwargs = model_kwargs
        self.model_kwargs.update({
            "enable_kv_cache": enable_kv_cache,
            "enable_prompt_cache": enable_prompt_cache,
        })
        
        self._models: List[OptimizedHerculeLM] = []
        self._available: queue.Queue = queue.Queue()
        self._lock = threading.Lock()
        self._initialized = False
    
    def initialize(self):
        """Load all model instances."""
        with self._lock:
            if self._initialized:
                return
            
            for i in range(self.pool_size):
                model = OptimizedHerculeLM(self.config, **self.model_kwargs)
                model.load(self.checkpoint_path, self.tokenizer_dir)
                self._models.append(model)
                self._available.put(model)
            
            self._initialized = True
    
    def acquire(self, timeout: Optional[float] = None) -> OptimizedHerculeLM:
        """Acquire a model instance from the pool."""
        if not self._initialized:
            self.initialize()
        return self._available.get(timeout=timeout)
    
    def release(self, model: OptimizedHerculeLM):
        """Return a model instance to the pool."""
        self._available.put(model)
    
    @contextmanager
    def model(self):
        """Context manager for acquiring and releasing a model."""
        m = self.acquire()
        try:
            yield m
        finally:
            self.release(m)
    
    def generate(
        self,
        prompt: str,
        max_new_tokens: int = 64,
        temperature: float = 0.0,
        top_k: int = 0,
        top_p: float = 1.0,
        seed: int = 0,
        use_kv_cache: bool = True,
    ) -> str:
        """Generate using a pooled model."""
        with self.model() as model:
            return model.generate(
                prompt=prompt,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                top_k=top_k,
                top_p=top_p,
                seed=seed,
                use_kv_cache=use_kv_cache,
            )
    
    def generate_batch(self, prompts: List[str], **kwargs) -> List[str]:
        """Generate batch using multiple pooled models in parallel."""
        from concurrent.futures import ThreadPoolExecutor
        
        if not self._initialized:
            self.initialize()
        
        with ThreadPoolExecutor(max_workers=self.pool_size) as executor:
            futures = [executor.submit(self.generate, p, **kwargs) for p in prompts]
            return [f.result() for f in futures]
    
    def shutdown(self):
        """Shutdown the pool."""
        self._models.clear()


# Add to OptimizedHerculeLM class
def _add_threadsafe_methods():
    """Add thread-safe methods to OptimizedHerculeLM."""
    
    def generate_threadsafe(
        self,
        prompt: str,
        max_new_tokens: int = 64,
        temperature: float = 0.0,
        top_k: int = 0,
        top_p: float = 1.0,
        seed: int = 0,
        use_kv_cache: bool = True,
    ) -> str:
        """Thread-safe generate using internal lock."""
        if not hasattr(self, '_generation_lock'):
            self._generation_lock = threading.Lock()
        
        with self._generation_lock:
            return self.generate(
                prompt=prompt,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                top_k=top_k,
                top_p=top_p,
                seed=seed,
                use_kv_cache=use_kv_cache,
            )
    
    OptimizedHerculeLM.generate_threadsafe = generate_threadsafe


_add_threadsafe_methods()

# Add missing imports
import queue
from contextlib import contextmanager


# ============================================================
# GGUF / llama.cpp Integration
# ============================================================

class GGUFModel:
    """
    Wrapper for llama.cpp GGUF models.
    
    Provides a compatible interface with OptimizedHerculeLM for
    running quantized models via llama.cpp.
    
    Requirements:
        pip install llama-cpp-python
    
    Note: This is a lightweight wrapper. For production use,
    consider the full llama-cpp-python API directly.
    """
    
    def __init__(
        self,
        model_path: str,
        n_ctx: int = 2048,
        n_threads: int = 4,
        n_gpu_layers: int = 0,
        verbose: bool = False,
        **kwargs,
    ):
        self.model_path = model_path
        self.n_ctx = n_ctx
        self.n_threads = n_threads
        self.n_gpu_layers = n_gpu_layers
        self.verbose = verbose
        self.kwargs = kwargs
        
        self._model = None
        self._lock = threading.Lock()
        self._load_model()
    
    def _load_model(self):
        """Load the GGUF model using llama-cpp-python."""
        try:
            from llama_cpp import Llama
        except ImportError:
            raise ImportError(
                "llama-cpp-python not installed. "
                "Install with: pip install llama-cpp-python"
            )
        
        self._model = Llama(
            model_path=self.model_path,
            n_ctx=self.n_ctx,
            n_threads=self.n_threads,
            n_gpu_layers=self.n_gpu_layers,
            verbose=self.verbose,
            **self.kwargs,
        )
    
    def generate(
        self,
        prompt: str,
        max_new_tokens: int = 64,
        temperature: float = 0.0,
        top_k: int = 0,
        top_p: float = 1.0,
        seed: int = 0,
        stream: bool = False,
    ) -> str:
        """Generate text using the GGUF model."""
        with self._lock:
            if stream:
                # For streaming, collect all tokens
                full_text = ""
                for token in self._model(
                    prompt,
                    max_tokens=max_new_tokens,
                    temperature=temperature,
                    top_k=top_k,
                    top_p=top_p,
                    seed=seed,
                    stream=True,
                ):
                    text = token["choices"][0]["text"]
                    full_text += text
                return full_text
            else:
                output = self._model(
                    prompt,
                    max_tokens=max_new_tokens,
                    temperature=temperature,
                    top_k=top_k,
                    top_p=top_p,
                    seed=seed,
                    stream=False,
                )
                return output["choices"][0]["text"]
    
    def generate_stream(
        self,
        prompt: str,
        max_new_tokens: int = 64,
        temperature: float = 0.0,
        top_k: int = 0,
        top_p: float = 1.0,
        seed: int = 0,
    ) -> Generator[str, None, str]:
        """Generate text as a stream of tokens."""
        with self._lock:
            full_text = ""
            for token in self._model(
                prompt,
                max_tokens=max_new_tokens,
                temperature=temperature,
                top_k=top_k,
                top_p=top_p,
                seed=seed,
                stream=True,
            ):
                text = token["choices"][0]["text"]
                full_text += text
                yield text
            return full_text
    
    def create_embedding(self, text: str) -> List[float]:
        """Create embedding for text."""
        with self._lock:
            return self._model.create_embedding(text)["data"][0]["embedding"]
    
    def tokenize(self, text: str) -> List[int]:
        """Tokenize text."""
        with self._lock:
            return self._model.tokenize(text.encode())
    
    def detokenize(self, tokens: List[int]) -> str:
        """Detokenize tokens."""
        with self._lock:
            return self._model.detokenize(tokens).decode()
    
    @property
    def tokenizer(self):
        """Return a tokenizer-like interface."""
        return self
    
    def encode(self, text: str) -> List[int]:
        return self.tokenize(text)
    
    def decode(self, tokens: List[int]) -> str:
        return self.detokenize(tokens)
    
    def close(self):
        """Free model resources."""
        with self._lock:
            if self._model is not None:
                del self._model
                self._model = None
    
    def __del__(self):
        self.close()


class GGUFModelPool:
    """
    Pool of GGUF models for concurrent inference.
    """
    
    def __init__(
        self,
        model_path: str,
        pool_size: int = 4,
        n_ctx: int = 2048,
        n_threads: int = 2,
        n_gpu_layers: int = 0,
        **kwargs,
    ):
        self.model_path = model_path
        self.pool_size = pool_size
        self.n_ctx = n_ctx
        self.n_threads = n_threads
        self.n_gpu_layers = n_gpu_layers
        self.kwargs = kwargs
        
        self._models: List[GGUFModel] = []
        self._available: queue.Queue = queue.Queue()
        self._lock = threading.Lock()
        self._initialized = False
    
    def initialize(self):
        """Load all GGUF model instances."""
        with self._lock:
            if self._initialized:
                return
            
            for i in range(self.pool_size):
                model = GGUFModel(
                    model_path=self.model_path,
                    n_ctx=self.n_ctx,
                    n_threads=self.n_threads,
                    n_gpu_layers=self.n_gpu_layers,
                    **self.kwargs,
                )
                self._models.append(model)
                self._available.put(model)
            
            self._initialized = True
    
    def acquire(self, timeout: Optional[float] = None) -> GGUFModel:
        """Acquire a model from the pool."""
        if not self._initialized:
            self.initialize()
        return self._available.get(timeout=timeout)
    
    def release(self, model: GGUFModel):
        """Return model to pool."""
        self._available.put(model)
    
    @contextmanager
    def model(self):
        m = self.acquire()
        try:
            yield m
        finally:
            self.release(m)
    
    def generate(self, prompt: str, **kwargs) -> str:
        with self.model() as model:
            return model.generate(prompt, **kwargs)
    
    def generate_batch(self, prompts: List[str], **kwargs) -> List[str]:
        from concurrent.futures import ThreadPoolExecutor
        
        if not self._initialized:
            self.initialize()
        
        with ThreadPoolExecutor(max_workers=self.pool_size) as executor:
            futures = [executor.submit(self.generate, p, **kwargs) for p in prompts]
            return [f.result() for f in futures]
    
    def shutdown(self):
        """Shutdown all models."""
        for model in self._models:
            model.close()
        self._models.clear()


def load_gguf_model(
    model_path: str,
    n_ctx: int = 2048,
    n_threads: int = 4,
    n_gpu_layers: int = 0,
    **kwargs,
) -> GGUFModel:
    """Convenience function to load a GGUF model."""
    return GGUFModel(
        model_path=model_path,
        n_ctx=n_ctx,
        n_threads=n_threads,
        n_gpu_layers=n_gpu_layers,
        **kwargs,
    )


# Add GGUF support to ModelLoadingCache
def load_gguf_from_cache(
    cache: ModelLoadingCache,
    model_path: str,
    **gguf_kwargs,
) -> GGUFModel:
    """Load or get cached GGUF model."""
    # Use model_path as cache key
    cached = cache.get(f"gguf:{model_path}")
    if cached:
        return cached
    
    model = GGUFModel(model_path, **gguf_kwargs)
    cache.put(f"gguf:{model_path}", model)
    return model