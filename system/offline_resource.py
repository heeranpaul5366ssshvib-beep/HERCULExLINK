from __future__ import annotations
"""HERCULE PC-Frontier: Offline-First Mode and Resource Policy.

Features:
- Offline mode detection and operation
- Graceful degradation when external providers unavailable
- Resource policy: never exceed available RAM
- Automatic fallback hierarchy
"""

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Callable
from pathlib import Path

from system.hardware import get_hardware_inventory, get_runtime_profile, RuntimeProfile, get_profile_config
from models.router.model_router import ModelRouter
from models.router.pc_frontier_router import PCFRouter, TaskClassification, TaskType

logger = logging.getLogger("HERCULE.PCFrontier.OfflineResource")


class ProviderStatus(str, Enum):
    """Status of a model provider."""
    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


@dataclass
class ProviderHealth:
    """Health status of a provider."""
    name: str
    status: ProviderStatus = ProviderStatus.UNKNOWN
    latency_ms: float = 0.0
    error: Optional[str] = None
    last_check: float = 0.0
    consecutive_failures: int = 0


@dataclass
class ResourceLimits:
    """Resource limits for the current profile."""
    max_memory_mb: float
    max_model_params: int
    max_context_tokens: int
    reserved_memory_mb: float = 512  # System reserve


class OfflineModeManager:
    """Manage offline-first operation with graceful degradation."""
    
    def __init__(
        self,
        router: PCFRouter,
        hardware_inventory=None,
        check_interval: float = 30.0,
    ):
        self.router = router
        self.hardware = hardware_inventory or get_hardware_inventory()
        self.profile = get_runtime_profile()
        self.profile_config = get_profile_config(self.profile)
        self.check_interval = check_interval
        
        # Offline state
        self._offline_mode = False
        self._forced_offline = False
        self._provider_health: Dict[str, ProviderHealth] = {}
        self._health_check_thread: Optional[threading.Thread] = None
        self._running = False
        
        # Fallback hierarchy
        self.fallback_chain = [
            "hercule-lm",      # Native (always available offline)
            "builtin",         # Local GGUF
            "transformers",    # Local transformers
            "ollama",          # Local Ollama
            "mock",            # Last resort
        ]
        
        # Initialize provider health
        self._init_provider_health()
    
    def _init_provider_health(self):
        """Initialize health tracking for all providers."""
        for provider in self.fallback_chain:
            self._provider_health[provider] = ProviderHealth(
                name=provider,
                status=ProviderStatus.UNKNOWN,
            )
    
    def start(self):
        """Start health monitoring."""
        if self._running:
            return
        
        self._running = True
        self._health_check_thread = threading.Thread(
            target=self._health_check_loop,
            daemon=True,
        )
        self._health_check_thread.start()
        logger.info("Offline mode manager started")
    
    def stop(self):
        """Stop health monitoring."""
        self._running = False
        if self._health_check_thread:
            self._health_check_thread.join(timeout=5.0)
        logger.info("Offline mode manager stopped")
    
    def _health_check_loop(self):
        """Background health check loop."""
        while self._running:
            self._check_all_providers()
            time.sleep(self.check_interval)
    
    def _check_all_providers(self):
        """Check health of all providers."""
        base_router = self.router.base_router
        adapters = getattr(base_router, 'adapters', {})
        
        for name, adapter in adapters.items():
            health = self._provider_health.get(name)
            if not health:
                health = ProviderHealth(name=name)
                self._provider_health[name] = health
            
            try:
                start = time.perf_counter()
                if hasattr(adapter, "health"):
                    result = adapter.health()
                    health.latency_ms = (time.perf_counter() - start) * 1000
                    
                    if result.get("available", False):
                        health.status = ProviderStatus.AVAILABLE
                        health.consecutive_failures = 0
                    else:
                        health.status = ProviderStatus.DEGRADED
                        health.consecutive_failures += 1
                        health.error = result.get("reason", "Unknown")
                else:
                    health.status = ProviderStatus.AVAILABLE
                    health.consecutive_failures = 0
            except Exception as e:
                health.status = ProviderStatus.UNAVAILABLE
                health.consecutive_failures += 1
                health.error = str(e)
            
            health.last_check = time.time()
        
        # Update offline mode based on provider availability
        self._update_offline_mode()
    
    def _update_offline_mode(self):
        """Update offline mode based on provider availability."""
        # Check if any external provider is available
        external_available = any(
            h.status == ProviderStatus.AVAILABLE 
            for n, h in self._provider_health.items() 
            if n not in ("hercule-lm", "builtin", "mock", "transformers")
        )
        
        native_available = (
            self._provider_health.get("hercule-lm", ProviderHealth("hercule-lm")).status == ProviderStatus.AVAILABLE or
            self._provider_health.get("builtin", ProviderHealth("builtin")).status == ProviderStatus.AVAILABLE
        )
        
        # Force offline if no external providers and native is available
        was_offline = self._offline_mode
        self._offline_mode = not external_available and native_available
        
        if self._offline_mode != was_offline:
            logger.info(f"Offline mode changed: {was_offline} -> {self._offline_mode}")
            if self._offline_mode:
                logger.warning("External providers unavailable, operating in offline mode")
    
    def force_offline(self, enabled: bool = True):
        """Force offline mode."""
        self._forced_offline = enabled
        self._offline_mode = enabled
        logger.info(f"Offline mode forced: {enabled}")
    
    def is_offline(self) -> bool:
        """Check if in offline mode."""
        return self._offline_mode or self._forced_offline
    
    def get_available_providers(self) -> List[str]:
        """Get list of currently available providers in priority order."""
        available = []
        for name in self.fallback_chain:
            health = self._provider_health.get(name)
            if health and health.status == ProviderStatus.AVAILABLE:
                available.append(name)
        return available
    
    def get_degraded_providers(self) -> List[str]:
        """Get list of degraded providers."""
        return [
            name for name, health in self._provider_health.items()
            if health.status == ProviderStatus.DEGRADED
        ]
    
    def get_provider_status(self) -> Dict[str, Any]:
        """Get status of all providers."""
        return {
            name: {
                "status": health.status.value,
                "latency_ms": health.latency_ms,
                "error": health.error,
                "last_check": health.last_check,
                "failures": health.consecutive_failures,
            }
            for name, health in self._provider_health.items()
        }
    
    def route_with_fallback(
        self,
        task: str,
        preferred_provider: Optional[str] = None,
    ) -> Tuple[str, Any]:
        """
        Route with automatic fallback.
        
        Returns (provider_name, adapter) or raises if all fail.
        """
        # Build candidate list
        candidates = []
        
        if preferred_provider:
            candidates.append(preferred_provider)
        
        # Add fallback chain
        for name in self.fallback_chain:
            if name not in candidates:
                candidates.append(name)
        
        # Filter to available (or degraded in offline mode)
        for name in candidates:
            health = self._provider_health.get(name)
            if health and health.status in (ProviderStatus.AVAILABLE, ProviderStatus.DEGRADED):
                # Try to get adapter
                adapter = getattr(self.router.base_router, 'adapters', {}).get(name)
                if adapter:
                    return name, adapter
        
        # Last resort: try any registered adapter
        base_router = self.router.base_router
        for name, adapter in getattr(base_router, 'adapters', {}).items():
            return name, adapter
        
        raise RuntimeError("No available model providers")
    
    def get_status_summary(self) -> Dict[str, Any]:
        """Get summary for UI/HUD."""
        return {
            "offline_mode": self.is_offline(),
            "forced_offline": self._forced_offline,
            "profile": self.profile.value,
            "available_providers": self.get_available_providers(),
            "degraded_providers": self.get_degraded_providers(),
            "provider_details": self.get_provider_status(),
        }


class ResourcePolicy:
    """Enforce resource limits - never exceed available RAM."""
    
    def __init__(self, hardware_inventory=None):
        self.hardware = hardware_inventory or get_hardware_inventory()
        self.profile = get_runtime_profile()
        self.profile_config = get_profile_config(self.profile)
        self.limits = ResourceLimits(
            max_memory_mb=self.profile_config["memory_limit_mb"],
            max_model_params=self.profile_config["max_model_params"],
            max_context_tokens=self.profile_config["max_context_tokens"],
        )
        self._allocations: Dict[str, float] = {}  # model_name -> memory_mb
        self._lock = threading.Lock()
    
    def can_allocate(self, model_params: int, quantized: bool = False, context_tokens: int = 2048) -> bool:
        """Check if a model can be loaded within limits."""
        from system.hardware import estimate_model_memory
        
        estimated_mb = estimate_model_memory(model_params, quantized, context_tokens)
        
        with self._lock:
            current_allocated = sum(self._allocations.values())
            available = self.limits.max_memory_mb - self.limits.reserved_memory_mb - current_allocated
            
            return estimated_mb <= available
    
    def allocate(self, model_name: str, model_params: int, quantized: bool = False, context_tokens: int = 2048) -> bool:
        """Allocate memory for a model."""
        from system.hardware import estimate_model_memory
        
        estimated_mb = estimate_model_memory(model_params, quantized, context_tokens)
        
        with self._lock:
            current_allocated = sum(self._allocations.values())
            available = self.limits.max_memory_mb - self.limits.reserved_memory_mb - current_allocated
            
            if estimated_mb > available:
                logger.warning(f"Cannot allocate {estimated_mb:.0f}MB for {model_name}: only {available:.0f}MB available")
                return False
            
            self._allocations[model_name] = estimated_mb
            logger.info(f"Allocated {estimated_mb:.0f}MB for {model_name}")
            return True
    
    def deallocate(self, model_name: str) -> bool:
        """Deallocate memory for a model."""
        with self._lock:
            if model_name in self._allocations:
                freed = self._allocations.pop(model_name)
                logger.info(f"Deallocated {freed:.0f}MB for {model_name}")
                return True
            return False
    
    def get_memory_status(self) -> Dict[str, Any]:
        """Get current memory allocation status."""
        with self._lock:
            allocated = sum(self._allocations.values())
            return {
                "limit_mb": self.limits.max_memory_mb,
                "reserved_mb": self.limits.reserved_memory_mb,
                "allocated_mb": allocated,
                "available_mb": self.limits.max_memory_mb - self.limits.reserved_memory_mb - allocated,
                "allocations": dict(self._allocations),
                "profile": self.profile.value,
            }
    
    def get_model_limits(self) -> Dict[str, Any]:
        """Get model loading limits."""
        return {
            "max_model_params": self.limits.max_model_params,
            "max_context_tokens": self.limits.max_context_tokens,
            "max_memory_mb": self.limits.max_memory_mb,
        }
    
    def select_model_for_task(
        self,
        available_models: List[Dict[str, Any]],
        task_complexity: float,
    ) -> Optional[Dict[str, Any]]:
        """Select best model that fits resource constraints."""
        # Filter to models that fit
        fitting = []
        for model in available_models:
            params = model.get("params", 0)
            if params <= self.limits.max_model_params:
                # Estimate memory
                from system.hardware import estimate_model_memory
                mem = estimate_model_memory(params, True, self.limits.max_context_tokens)
                if mem <= self.limits.max_memory_mb:
                    fitting.append((model, mem))
        
        if not fitting:
            return None
        
        # Select based on task complexity
        # Simple tasks -> smaller models
        # Complex tasks -> larger models (within limits)
        fitting.sort(key=lambda x: x[1])
        
        if task_complexity < 0.3:
            return fitting[0][0]  # Smallest
        elif task_complexity < 0.7:
            return fitting[len(fitting) // 2][0]  # Medium
        else:
            return fitting[-1][0]  # Largest


class GracefulDegradation:
    """Handle graceful degradation when resources are constrained."""
    
    def __init__(
        self,
        resource_policy: ResourcePolicy,
        offline_manager: OfflineModeManager,
    ):
        self.resources = resource_policy
        self.offline = offline_manager
    
    def handle_external_unavailable(self, task: str) -> Dict[str, Any]:
        """Handle case when external models are unavailable."""
        classification = self.offline.router.classify_task(task)
        
        # Determine best local option
        local_providers = ["hercule-lm", "builtin", "transformers"]
        available_local = [
            p for p in local_providers 
            if self.offline._provider_health.get(p, ProviderHealth(p)).status 
            in (ProviderStatus.AVAILABLE, ProviderStatus.DEGRADED)
        ]
        
        if not available_local:
            return {
                "success": False,
                "reason": "No local models available",
                "fallback": "mock",
            }
        
        # Route to best local provider
        provider = available_local[0]
        adapter = getattr(self.offline.router.base_router, 'adapters', {}).get(provider)
        
        return {
            "success": True,
            "provider": provider,
            "adapter": adapter,
            "degraded": True,
            "message": f"Using local {provider} (external unavailable)",
        }
    
    def handle_memory_pressure(self) -> Dict[str, Any]:
        """Handle memory pressure by unloading models."""
        status = self.resources.get_memory_status()
        
        if status["available_mb"] < 256:
            # Critical: need to free memory
            # Unload largest model
            if status["allocations"]:
                largest = max(status["allocations"], key=status["allocations"].get)
                self.resources.deallocate(largest)
                
                return {
                    "action": "unloaded_model",
                    "model": largest,
                    "freed_mb": status["allocations"].get(largest, 0),
                }
        
        return {"action": "none", "memory_status": status}
    
    def adjust_for_profile(self, profile: RuntimeProfile) -> Dict[str, Any]:
        """Adjust settings for a new profile."""
        from system.hardware import get_profile_config
        
        config = get_profile_config(profile)
        
        return {
            "max_context_tokens": config["max_context_tokens"],
            "batch_size": config["batch_size"],
            "num_threads": config["num_threads"],
            "use_quantization": config["use_quantization"],
            "enable_streaming": config["enable_streaming"],
            "prefer_native": config["prefer_native_lm"],
        }


def create_offline_manager(router: PCFRouter) -> OfflineModeManager:
    """Factory for offline mode manager."""
    return OfflineModeManager(router)


def create_resource_policy() -> ResourcePolicy:
    """Factory for resource policy."""
    return ResourcePolicy()


def create_graceful_degradation(
    resource_policy: ResourcePolicy,
    offline_manager: OfflineModeManager,
) -> GracefulDegradation:
    """Factory for graceful degradation handler."""
    return GracefulDegradation(resource_policy, offline_manager)