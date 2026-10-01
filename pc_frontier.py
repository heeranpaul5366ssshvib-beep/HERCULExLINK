from __future__ import annotations
"""HERCULE PC-Frontier: Main Integration Module.

Initializes all PC-Frontier components and provides unified interface.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from system.hardware import (
    get_hardware_inventory, get_runtime_profile, get_profile_config,
    RuntimeProfile, HardwareInventory, print_hardware_summary,
)
from models.router.pc_frontier_router import create_pc_frontier_router, PCFRouter
from models.streaming import create_streaming_engine, StreamingEngine
from models.hercule_lm.optimized_model import OptimizedHerculeLM, get_model_loading_cache
from memory.enhanced_memory_manager import create_enhanced_memory_manager, EnhancedMemoryManager
from cognition.context.enhanced_context_manager import create_enhanced_context_manager, EnhancedContextManager
from orchestrator.autonomous_engine import create_autonomous_engine, AutonomousEngine
from system.offline_resource import (
    create_offline_manager, create_resource_policy, create_graceful_degradation,
    OfflineModeManager, ResourcePolicy, GracefulDegradation,
)
from benchmark.pc_frontier_benchmark import run_benchmark_suite, PCFrontierBenchmark

logger = logging.getLogger("HERCULE.PCFrontier")


class PCFrontierSystem:
    """Main PC-Frontier system integrating all components."""
    
    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        enable_benchmark: bool = False,
    ):
        self.config = config or {}
        self.enable_benchmark = enable_benchmark
        
        # Initialize hardware detection first
        self.hardware = get_hardware_inventory()
        self.profile = get_runtime_profile()
        self.profile_config = get_profile_config(self.profile)
        
        logger.info(f"PC-Frontier initialized with profile: {self.profile.value}")
        
        # Initialize core components
        self._init_components()
        
        # Start offline manager
        self.offline_manager.start()
        
        # Run benchmark if enabled
        if self.enable_benchmark:
            self._run_benchmark()
    
    def _init_components(self):
        """Initialize all PC-Frontier components."""
        # Router
        self.router = create_pc_frontier_router()
        
        # Native model (for hercule-lm adapter)
        self._load_native_model()
        
        # Streaming engine (with native model)
        self.streaming = create_streaming_engine(self.router, self.native_model)
        
        # Memory (requires base memory manager)
        from memory.memory_manager import MemoryManager
        base_memory = MemoryManager()
        self.memory = create_enhanced_memory_manager(base_memory)
        
        # Context manager (requires model manager)
        from models.model_manager import ModelManager
        model_manager = ModelManager()
        self.context = create_enhanced_context_manager(self.memory, model_manager)
        
        # Autonomous engine
        self.autonomous = create_autonomous_engine(
            self.router, self.streaming, self.memory, self.context
        )
        
        # Offline manager
        self.offline_manager = create_offline_manager(self.router)
        
        # Resource policy
        self.resource_policy = create_resource_policy()
        
        # Graceful degradation
        self.degradation = create_graceful_degradation(
            self.resource_policy, self.offline_manager
        )
        
        # Native model cache
        self.model_cache = get_model_loading_cache()
    
    def _load_native_model(self):
        """Load the native HERCULE-LM model if available."""
        import json
        from pathlib import Path
        
        # Find the latest checkpoint
        checkpoints_root = Path("training/checkpoints")
        latest_checkpoint = None
        latest_step = -1
        
        if checkpoints_root.exists():
            for run_dir in checkpoints_root.iterdir():
                if not run_dir.is_dir():
                    continue
                for step_dir in run_dir.iterdir():
                    if step_dir.is_dir() and step_dir.name.startswith("step_"):
                        manifest_path = step_dir / "manifest.json"
                        if manifest_path.exists():
                            try:
                                with open(manifest_path, 'r') as f:
                                    manifest = json.load(f)
                                if manifest.get("architecture", {}).get("model_id") == "hercule-lm-micro":
                                    step_num = int(step_dir.name.replace("step_", ""))
                                    if step_num > latest_step:
                                        latest_step = step_num
                                        latest_checkpoint = str(step_dir)
                            except Exception:
                                pass
        
        if latest_checkpoint:
            logger.info(f"Loading native model from: {latest_checkpoint}")
            from models.hercule_lm.config import HerculeLMConfig
            from models.hercule_lm.tokenizer import HerculeBPETokenizer
            from models.hercule_lm import checkpoint as ckpt
            
            with open(Path(latest_checkpoint) / "manifest.json", 'r') as f:
                manifest = json.load(f)
            
            config = HerculeLMConfig.from_dict(manifest['architecture'])
            self.native_model = OptimizedHerculeLM(config, enable_kv_cache=True, enable_prompt_cache=True)
            self.native_model.load(latest_checkpoint, r"training/tokenizer/hercule-bpe-micro-v1")
            logger.info("Native HERCULE-LM loaded successfully")
        else:
            logger.warning("No native HERCULE-LM checkpoint found")
            self.native_model = None
    
    def _run_benchmark(self):
        """Run performance benchmark."""
        logger.info("Running benchmark suite...")
        self.benchmark = run_benchmark_suite(
            router=self.router,
            streaming=self.streaming,
            memory=self.memory,
            context=self.context,
            autonomous=self.autonomous,
        )
    
    def process(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Process a prompt through the full PC-Frontier pipeline."""
        # Classify task
        classification = self.router.classify_task(prompt)
        
        # Route to best model
        decision = self.router.route(prompt)
        
        # Check for tool-first
        if decision.model.startswith("tool:"):
            tool_name = decision.model.split(":", 1)[1]
            return {
                "type": "tool",
                "tool": tool_name,
                "result": self._execute_tool(tool_name, prompt),
            }
        
        # Build optimized context
        context = self.context.build_context(
            goal=prompt,
            provider=decision.adapter_name,
            model=decision.model,
        )
        
        # Stream response
        task_id = self.streaming.start_stream(
            prompt,
            stream=True,
            verify=self.profile_config.get("verification_required", True),
        )
        
        response = self.streaming.wait_for_complete(task_id, timeout=120.0)
        
        # Verify if needed
        verification = None
        if classification.requires_verification:
            verification = self.router.verify_output(
                response.final_content,
                classification.requires_verification,
            )
        
        return {
            "type": "model",
            "model": decision.model,
            "provider": decision.adapter_name,
            "content": response.final_content,
            "latency_ms": response.total_latency_ms,
            "first_token_ms": response.first_token_latency_ms,
            "verification": verification,
            "context_tokens": context.total_tokens,
        }
    
    def _execute_tool(self, tool_name: str, prompt: str) -> str:
        """Execute a deterministic tool."""
        if tool_name == "calculator":
            import re
            expr = re.search(r'(\d+(?:\s*[\+\-\*/]\s*\d+)+)', prompt)
            if expr:
                try:
                    return f"Result: {eval(expr.group())}"
                except Exception as e:
                    return f"Error: {e}"
            return "Could not calculate"
        return f"Tool {tool_name} executed"
    
    def start_autonomous_task(self, goal: str, **kwargs) -> str:
        """Start an autonomous task."""
        return self.autonomous.start_task(goal, **kwargs)
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status."""
        return {
            "profile": self.profile.value,
            "hardware": {
                "cpu": f"{self.hardware.cpu.physical_cores}P/{self.hardware.cpu.logical_cores}L",
                "ram_mb": self.hardware.memory.available_mb,
                "gpu": self.hardware.gpu.primary_device_name,
            },
            "offline": self.offline_manager.is_offline(),
            "providers": self.offline_manager.get_available_providers(),
            "memory": self.resource_policy.get_memory_status(),
            "active_tasks": len(self.autonomous._tasks),
            "active_streams": len(self.streaming.get_active_streams()),
        }
    
    def shutdown(self):
        """Shutdown all components."""
        self.offline_manager.stop()
        logger.info("PC-Frontier shutdown complete")


def create_pc_frontier_system(
    config: Optional[Dict[str, Any]] = None,
    enable_benchmark: bool = False,
) -> PCFrontierSystem:
    """Factory for PC-Frontier system."""
    return PCFrontierSystem(config, enable_benchmark)


def main():
    """Main entry point for testing."""
    logging.basicConfig(level=logging.INFO)
    
    # Print hardware summary
    print_hardware_summary()
    
    # Create system
    system = create_pc_frontier_system(enable_benchmark=True)
    
    # Test processing
    test_prompts = [
        "Hello!",
        "What is 25 * 47?",
        "Write a Python hello world",
        "Explain quantum computing",
    ]
    
    for prompt in test_prompts:
        print(f"\n>>> {prompt}")
        result = system.process(prompt)
        print(f"[{result['type']}] {result.get('model', result.get('tool'))}: {result.get('content', result.get('result'))[:200]}")
    
    # Print status
    print("\nSystem Status:")
    status = system.get_system_status()
    for k, v in status.items():
        print(f"  {k}: {v}")
    
    system.shutdown()


if __name__ == "__main__":
    main()