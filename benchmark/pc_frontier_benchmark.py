from __future__ import annotations
"""HERCULE PC-Frontier: Performance Benchmark and Report Generator.

Measures real performance and generates reports.
"""

import json
import logging
import os
import statistics
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime, timezone

from system.hardware import get_hardware_inventory, HardwareInventory, RuntimeProfile, get_runtime_profile, get_profile_config
from models.hercule_lm.optimized_model import OptimizedHerculeLM, benchmark_generation
from models.router.pc_frontier_router import PCFRouter, TaskClassification, TaskType
from models.streaming import StreamingEngine
from memory.enhanced_memory_manager import EnhancedMemoryManager
from cognition.context.enhanced_context_manager import EnhancedContextManager
from orchestrator.autonomous_engine import AutonomousEngine, AutonomousTask
from system.offline_resource import OfflineModeManager, ResourcePolicy

logger = logging.getLogger("HERCULE.Benchmark")


@dataclass
class BenchmarkResult:
    """Single benchmark result."""
    name: str
    category: str
    value: float
    unit: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class BenchmarkSuite:
    """Collection of benchmark results."""
    suite_name: str
    hardware: HardwareInventory
    profile: RuntimeProfile
    results: List[BenchmarkResult] = field(default_factory=list)
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: Optional[str] = None
    duration_s: float = 0.0


class PCFrontierBenchmark:
    """Comprehensive benchmark for PC-Frontier."""
    
    def __init__(
        self,
        router: PCFRouter,
        streaming: StreamingEngine,
        memory: EnhancedMemoryManager,
        context: EnhancedContextManager,
        autonomous: AutonomousEngine,
        output_dir: str = "artifacts/performance",
    ):
        self.router = router
        self.streaming = streaming
        self.memory = memory
        self.context = context
        self.autonomous = autonomous
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.hardware = get_hardware_inventory()
        self.profile = get_runtime_profile()
        self.suite = BenchmarkSuite(
            suite_name="hercule_pc_frontier",
            hardware=self.hardware,
            profile=self.profile,
        )
    
    def run_all(self) -> BenchmarkSuite:
        """Run all benchmarks."""
        logger.info("Starting PC-Frontier benchmark suite")
        start_time = time.perf_counter()
        
        # 1. Hardware detection
        self._benchmark_hardware()
        
        # 2. Cold startup
        self._benchmark_cold_startup()
        
        # 3. Warm startup
        self._benchmark_warm_startup()
        
        # 4. Model load
        self._benchmark_model_load()
        
        # 5. First token latency
        self._benchmark_first_token()
        
        # 6. Tokens per second
        self._benchmark_tokens_per_sec()
        
        # 7. Memory usage
        self._benchmark_memory_usage()
        
        # 8. Context construction
        self._benchmark_context_construction()
        
        # 9. Tool latency
        self._benchmark_tool_latency()
        
        # 10. End-to-end task latency
        self._benchmark_e2e_latency()
        
        # 11. Routing accuracy
        self._benchmark_routing()
        
        # 12. Verification overhead
        self._benchmark_verification()
        
        # 13. Streaming latency
        self._benchmark_streaming()
        
        # 14. Memory retrieval
        self._benchmark_memory_retrieval()
        
        # 15. Autonomous task
        self._benchmark_autonomous()
        
        self.suite.completed_at = datetime.now(timezone.utc).isoformat()
        self.suite.duration_s = time.perf_counter() - start_time
        
        logger.info(f"Benchmark completed in {self.suite.duration_s:.2f}s")
        return self.suite
    
    def _add_result(self, name: str, category: str, value: float, unit: str, **metadata):
        """Add a benchmark result."""
        self.suite.results.append(BenchmarkResult(
            name=name,
            category=category,
            value=value,
            unit=unit,
            metadata=metadata,
        ))
    
    def _benchmark_hardware(self):
        """Record hardware configuration."""
        self._add_result(
            "cpu_cores", "hardware",
            self.hardware.cpu.logical_cores, "cores",
            physical=self.hardware.cpu.physical_cores,
            model=self.hardware.cpu.model,
        )
        self._add_result(
            "ram_total_mb", "hardware",
            self.hardware.memory.total_mb, "MB",
        )
        self._add_result(
            "ram_available_mb", "hardware",
            self.hardware.memory.available_mb, "MB",
        )
        self._add_result(
            "gpu_available", "hardware",
            1.0 if self.hardware.gpu.cuda_available else 0.0, "bool",
            vram_mb=self.hardware.gpu.total_vram_mb,
        )
        self._add_result(
            "profile", "hardware",
            1.0, "enum",
            profile_value=self.profile.value,
        )
    
    def _benchmark_cold_startup(self):
        """Measure cold startup time."""
        # Time to initialize all components
        start = time.perf_counter()
        
        # Simulate cold start by creating new instances
        from models.router.pc_frontier_router import create_pc_frontier_router
        from models.streaming import create_streaming_engine
        from cognition.context.enhanced_context_manager import create_enhanced_context_manager
        
        _ = create_pc_frontier_router()
        _ = create_streaming_engine(self.router)
        # Context manager needs memory manager - skip full init
        
        elapsed = (time.perf_counter() - start) * 1000
        self._add_result("cold_startup_ms", "latency", elapsed, "ms")
    
    def _benchmark_warm_startup(self):
        """Measure warm startup (already initialized)."""
        start = time.perf_counter()
        
        # Just route a simple task
        _ = self.router.route("hello")
        
        elapsed = (time.perf_counter() - start) * 1000
        self._add_result("warm_startup_ms", "latency", elapsed, "ms")
    
    def _benchmark_model_load(self):
        """Benchmark model loading time."""
        # This would need a real model checkpoint
        # For now, measure router initialization
        start = time.perf_counter()
        
        for _ in range(5):
            _ = self.router.route("test task")
        
        elapsed = (time.perf_counter() - start) * 1000 / 5
        self._add_result("avg_route_ms", "latency", elapsed, "ms")
    
    def _benchmark_first_token(self):
        """Measure first token latency."""
        # Use streaming engine
        task_id = self.streaming.start_stream(
            "What is 2+2?",
            stream=True,
        )
        
        # Wait for first token
        start = time.perf_counter()
        first_token = None
        while first_token is None:
            chunks = self.streaming.get_chunks(task_id)
            for chunk in chunks:
                if chunk.state.value == "generating" and chunk.content:
                    first_token = chunk
                    break
            if first_token:
                break
            time.sleep(0.01)
        
        elapsed = (time.perf_counter() - start) * 1000
        self._add_result("first_token_ms", "latency", elapsed, "ms")
        
        # Wait for complete
        self.streaming.wait_for_complete(task_id, timeout=30.0)
    
    def _benchmark_tokens_per_sec(self):
        """Measure sustained token generation rate."""
        prompts = [
            "Write a short story about a robot.",
            "Explain quantum computing.",
            "List the planets in order.",
        ]
        
        results = []
        for prompt in prompts:
            task_id = self.streaming.start_stream(prompt, stream=True)
            response = self.streaming.wait_for_complete(task_id, timeout=60.0)
            
            if response.total_latency_ms > 0:
                # Estimate tokens
                tokens = len(response.final_content) / 4  # Rough estimate
                tps = tokens / (response.total_latency_ms / 1000)
                results.append(tps)
        
        if results:
            self._add_result(
                "tokens_per_sec", "throughput",
                statistics.mean(results), "tok/s",
                min=min(results), max=max(results),
                samples=len(results),
            )
    
    def _benchmark_memory_usage(self):
        """Measure memory usage."""
        import psutil
        process = psutil.Process()
        
        # Baseline
        baseline = process.memory_info().rss / 1e6
        
        # Run some operations
        for _ in range(10):
            self.router.route("test task")
            self.memory.retrieve_rank_compact_inject("test query", limit=5)
        
        # Peak
        peak = process.memory_info().rss / 1e6
        
        self._add_result("baseline_memory_mb", "memory", baseline, "MB")
        self._add_result("peak_memory_mb", "memory", peak, "MB")
        self._add_result("memory_delta_mb", "memory", peak - baseline, "MB")
    
    def _benchmark_context_construction(self):
        """Measure context building time."""
        from cognition.context.context_manager import ContextDiagnostics
        
        times = []
        for _ in range(10):
            start = time.perf_counter()
            _ = self.context.build_context(
                goal="Test task",
                system_prompt="You are a helpful assistant.",
                provider=self.router.base_router.adapters.keys() and list(self.router.base_router.adapters.keys())[0] or "unknown",
            )
            times.append((time.perf_counter() - start) * 1000)
        
        self._add_result(
            "context_build_ms", "latency",
            statistics.mean(times), "ms",
            min=min(times), max=max(times),
        )
    
    def _benchmark_tool_latency(self):
        """Measure tool execution latency."""
        tools = ["calculator", "filesystem", "code_executor"]
        
        for tool in tools:
            times = []
            for _ in range(5):
                start = time.perf_counter()
                _ = self.router.route(f"Use {tool} to test")
                times.append((time.perf_counter() - start) * 1000)
            
            self._add_result(
                f"tool_{tool}_ms", "latency",
                statistics.mean(times), "ms",
            )
    
    def _benchmark_e2e_latency(self):
        """Measure end-to-end task latency."""
        tasks = [
            ("chat", "Hello, how are you?"),
            ("calculation", "What is 25 * 47?"),
            ("reasoning", "Explain why the sky is blue."),
            ("coding", "Write a hello world in Python."),
        ]
        
        for category, prompt in tasks:
            start = time.perf_counter()
            task_id = self.streaming.start_stream(prompt)
            response = self.streaming.wait_for_complete(task_id, timeout=60.0)
            elapsed = (time.perf_counter() - start) * 1000
            
            self._add_result(
                f"e2e_{category}_ms", "latency",
                elapsed, "ms",
            )
    
    def _benchmark_routing(self):
        """Benchmark routing accuracy and speed."""
        test_cases = [
            (TaskType.CHAT, "Hello there"),
            (TaskType.CALCULATION, "Calculate 15 * 23"),
            (TaskType.CODING, "Write a Python function"),
            (TaskType.FILE_OPERATION, "Read the config file"),
            (TaskType.RESEARCH, "Research quantum computing"),
            (TaskType.PLANNING, "Plan a project release"),
            (TaskType.AUTOMATION, "Automate the backup"),
            (TaskType.REASONING, "Why does this happen?"),
            (TaskType.SYSTEM_TASK, "Check system status"),
        ]
        
        correct = 0
        times = []
        
        for expected_type, prompt in test_cases:
            start = time.perf_counter()
            classification = self.router.classify_task(prompt)
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)
            
            if classification.task_type == expected_type:
                correct += 1
        
        accuracy = correct / len(test_cases)
        self._add_result(
            "routing_accuracy", "quality",
            accuracy, "ratio",
            correct=correct, total=len(test_cases),
        )
        self._add_result(
            "classification_ms", "latency",
            statistics.mean(times), "ms",
        )
    
    def _benchmark_verification(self):
        """Measure verification overhead."""
        from models.hercule_lm.verifiers import verify_math, verify_json, verify_verification
        
        verifiers = [
            ("math", lambda: verify_math("42", "42")),
            ("json", lambda: verify_json('{"key": "value"}')),
            ("verification", lambda: verify_verification("CORRECT", "CORRECT|")),
        ]
        
        for name, verify_fn in verifiers:
            times = []
            for _ in range(100):
                start = time.perf_counter()
                verify_fn()
                times.append((time.perf_counter() - start) * 1000)
            
            self._add_result(
                f"verify_{name}_ms", "latency",
                statistics.mean(times), "ms",
                p99=sorted(times)[98],
            )
    
    def _benchmark_streaming(self):
        """Measure streaming overhead."""
        # Compare streaming vs non-streaming
        prompt = "Write a paragraph about AI."
        
        # Non-streaming
        start = time.perf_counter()
        task_id = self.streaming.start_stream(prompt, stream=False)
        _ = self.streaming.wait_for_complete(task_id)
        non_stream_ms = (time.perf_counter() - start) * 1000
        
        # Streaming
        start = time.perf_counter()
        task_id = self.streaming.start_stream(prompt, stream=True)
        _ = self.streaming.wait_for_complete(task_id)
        stream_ms = (time.perf_counter() - start) * 1000
        
        self._add_result("streaming_overhead_ms", "latency", stream_ms - non_stream_ms, "ms")
        self._add_result("non_streaming_ms", "latency", non_stream_ms, "ms")
        self._add_result("streaming_ms", "latency", stream_ms, "ms")
    
    def _benchmark_memory_retrieval(self):
        """Measure memory retrieval performance."""
        queries = [
            "project configuration",
            "coding best practices",
            "file operations",
            "debugging tips",
        ]
        
        times = []
        for query in queries:
            start = time.perf_counter()
            _ = self.memory.retrieve_rank_compact_inject(query, limit=5)
            times.append((time.perf_counter() - start) * 1000)
        
        self._add_result(
            "memory_retrieval_ms", "latency",
            statistics.mean(times), "ms",
        )
    
    def _benchmark_autonomous(self):
        """Benchmark autonomous task execution."""
        # Simple task
        task_id = self.autonomous.start_task("Calculate 10 + 5")
        task = self.autonomous.get_task(task_id)
        
        # Wait for completion
        while task and task.phase.value not in ("completed", "failed"):
            time.sleep(0.1)
            task = self.autonomous.get_task(task_id)
        
        if task:
            duration = (task.completed_at or time.time()) - (task.started_at or time.time())
            self._add_result(
                "autonomous_simple_s", "latency",
                duration, "s",
                steps=len(task.completed_steps),
            )
    
    def save_results(self, filename: Optional[str] = None) -> Path:
        """Save benchmark results to JSON."""
        if filename is None:
            filename = f"hercule_pc_frontier_benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        filepath = self.output_dir / filename
        
        # Convert to serializable format
        data = {
            "suite_name": self.suite.suite_name,
            "hardware": {
                "cpu": {
                    "model": self.hardware.cpu.model,
                    "physical_cores": self.hardware.cpu.physical_cores,
                    "logical_cores": self.hardware.cpu.logical_cores,
                },
                "memory": {
                    "total_mb": self.hardware.memory.total_mb,
                    "available_mb": self.hardware.memory.available_mb,
                },
                "gpu": {
                    "cuda_available": self.hardware.gpu.cuda_available,
                    "total_vram_mb": self.hardware.gpu.total_vram_mb,
                },
                "profile": self.profile.value,
            },
            "profile_config": getattr(self.profile, 'value', str(self.profile)),
            "started_at": self.suite.started_at,
            "completed_at": self.suite.completed_at,
            "duration_s": self.suite.duration_s,
            "results": [asdict(r) for r in self.suite.results],
        }
        
        filepath.write_text(json.dumps(data, indent=2))
        logger.info(f"Benchmark results saved to {filepath}")
        return filepath
    
    def generate_report(self, filename: Optional[str] = None) -> Path:
        """Generate markdown report."""
        if filename is None:
            filename = f"hercule_pc_frontier_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        
        filepath = self.output_dir / filename
        
        # Group results by category
        by_category: Dict[str, List[BenchmarkResult]] = {}
        for r in self.suite.results:
            by_category.setdefault(r.category, []).append(r)
        
        lines = [
            "# HERCULE PC-Frontier Performance Report",
            f"\n**Generated**: {self.suite.completed_at or datetime.now(timezone.utc).isoformat()}",
            f"**Duration**: {self.suite.duration_s:.2f}s",
            f"\n## Hardware Configuration",
            f"- **CPU**: {self.hardware.cpu.model} ({self.hardware.cpu.physical_cores}P/{self.hardware.cpu.logical_cores}L cores)",
            f"- **RAM**: {self.hardware.memory.total_mb:.0f} MB total, {self.hardware.memory.available_mb:.0f} MB available",
            f"- **GPU**: {'CUDA ' + str(self.hardware.gpu.total_vram_mb) + ' MB' if self.hardware.gpu.cuda_available else 'None'}",
            f"- **Profile**: {self.profile.value.upper()}",
            f"\n## Benchmark Results",
        ]
        
        for category, results in sorted(by_category.items()):
            lines.append(f"\n### {category.title()}")
            lines.append("| Metric | Value | Unit | Details |")
            lines.append("|--------|-------|------|---------|")
            
            for r in results:
                details = ", ".join(f"{k}={v}" for k, v in r.metadata.items())
                lines.append(f"| {r.name} | {r.value:.2f} | {r.unit} | {details} |")
        
        # Summary
        lines.append("\n## Summary")
        
        # Key metrics
        key_metrics = {
            "First Token Latency": "first_token_ms",
            "Tokens/Second": "tokens_per_sec",
            "Peak Memory": "peak_memory_mb",
            "Routing Accuracy": "routing_accuracy",
            "Context Build": "context_build_ms",
            "E2E Chat": "e2e_chat_ms",
            "E2E Calculation": "e2e_calculation_ms",
        }
        
        lines.append("\n| Metric | Value |")
        lines.append("|--------|-------|")
        for label, name in key_metrics.items():
            for r in self.suite.results:
                if r.name == name:
                    if r.unit == "ratio":
                        lines.append(f"| {label} | {r.value:.1%} |")
                    else:
                        lines.append(f"| {label} | {r.value:.2f} {r.unit} |")
                    break
        
        content = "\n".join(lines)
        filepath.write_text(content)
        logger.info(f"Report saved to {filepath}")
        return filepath
    
    def print_summary(self):
        """Print benchmark summary to console."""
        print("\n" + "="*60)
        print("HERCULE PC-FRONTIER BENCHMARK SUMMARY")
        print("="*60)
        print(f"Profile: {self.profile.value.upper()}")
        print(f"Duration: {self.suite.duration_s:.2f}s")
        print(f"Results: {len(self.suite.results)} metrics")
        
        # Key metrics
        for r in self.suite.results:
            if r.name in ("first_token_ms", "tokens_per_sec", "peak_memory_mb", 
                          "routing_accuracy", "context_build_ms"):
                print(f"  {r.name}: {r.value:.2f} {r.unit}")
        
        print("="*60 + "\n")


def run_benchmark_suite(
    router: PCFRouter,
    streaming: StreamingEngine,
    memory: EnhancedMemoryManager,
    context: EnhancedContextManager,
    autonomous: AutonomousEngine,
    output_dir: str = "artifacts/performance",
) -> PCFrontierBenchmark:
    """Run full benchmark suite and return results."""
    benchmark = PCFrontierBenchmark(
        router=router,
        streaming=streaming,
        memory=memory,
        context=context,
        autonomous=autonomous,
        output_dir=output_dir,
    )
    
    benchmark.run_all()
    benchmark.save_results()
    benchmark.generate_report()
    benchmark.print_summary()
    
    return benchmark


if __name__ == "__main__":
    # This would be run with actual initialized components
    print("Benchmark module ready. Use run_benchmark_suite() with initialized components.")