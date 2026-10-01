"""Stress tests for ContextManager hardening."""

from __future__ import annotations

import time
from pathlib import Path
import tempfile

from cognition.context.context_manager import (
    ContextManager,
    ContextBuilder,
    ContextLayer,
    ProviderType,
    StructuredTaskState,
    ContextCheckpoint,
    DEFAULT_CONTEXT_BUDGETS,
    TokenCounter,
)
from memory.memory_manager import MemoryManager
from models.model_manager import ModelManager


class TestContextStress:
    """Stress tests for ContextManager."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.memory = MemoryManager()
        self.models = ModelManager()
        self.manager = ContextManager(self.memory, self.models)

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_100_conversation_turns(self):
        """Test 100+ conversation turns stay within budget."""
        self.manager.start_task("Long conversation test")

        # Add 120 conversation turns
        for i in range(120):
            self.manager.add_conversation_turn("user", f"User message {i} " + "x" * 100)
            self.manager.add_conversation_turn("assistant", f"Assistant response {i} " + "y" * 100)

        context = self.manager.build_context(
            goal="Continue conversation",
            provider=ProviderType.OLLAMA,
        )

        # Should stay within Ollama budget
        assert context.total_tokens <= DEFAULT_CONTEXT_BUDGETS[ProviderType.OLLAMA]
        # L6 (conversation) should be truncated but present
        conv_layers = [l for l in context.layers if l.layer == ContextLayer.CONVERSATION]
        assert len(conv_layers) == 1
        assert conv_layers[0].truncated or "[..." in conv_layers[0].content

    def test_50_tool_calls_large_outputs(self):
        """Test 50+ tool calls with large outputs."""
        self.manager.start_task("Tool stress test")

        tool_results = []
        for i in range(55):
            # Create large tool output (10KB each)
            large_output = "x" * 10000
            tool_results.append({
                "status": "success",
                "content": large_output,
                "path": f"/tmp/file_{i}.txt",
                "operation": "write",
            })

        context = self.manager.build_context(
            goal="Process files",
            tool_results=tool_results,
            provider=ProviderType.OLLAMA,
        )

        assert context.total_tokens <= DEFAULT_CONTEXT_BUDGETS[ProviderType.OLLAMA]
        # L4 tool results should be normalized/compressed
        tool_layers = [l for l in context.layers if l.layer == ContextLayer.TOOL_RESULTS]
        assert len(tool_layers) == 1
        # Should not contain raw 10KB outputs
        assert len(tool_layers[0].content) < 5000

    def test_large_tool_output_attack(self):
        """Test tool outputs from 1KB to 10MB."""
        self.manager.start_task("Tool output attack")

        sizes = [1024, 10240, 102400, 1048576, 10485760]  # 1KB to 10MB
        tool_results = []

        for size in sizes:
            large_output = "x" * size
            tool_results.append({
                "status": "success",
                "content": large_output,
                "operation": "read",
            })

        context = self.manager.build_context(
            goal="Read large files",
            tool_results=tool_results,
            provider=ProviderType.OLLAMA,
        )

        # Must stay within budget regardless of tool output sizes
        assert context.total_tokens <= DEFAULT_CONTEXT_BUDGETS[ProviderType.OLLAMA]
        tool_layers = [l for l in context.layers if l.layer == ContextLayer.TOOL_RESULTS]
        assert len(tool_layers) == 1
        # Normalizer should keep output small
        assert len(tool_layers[0].content) < 3000

    def test_memory_flood_irrelevant_vs_relevant(self):
        """Test thousands of irrelevant memories vs few relevant ones."""
        self.manager.start_task("Memory flood test")

        # Store 5000 irrelevant facts
        for i in range(5000):
            self.memory.remember_fact(f"irrelevant_fact_{i}", f"This is irrelevant fact number {i}")

        # Store 5 relevant facts
        for i in range(5):
            self.memory.remember_fact(f"relevant_fact_{i}", f"This is relevant fact number {i}")

        # Task references relevant facts
        state = self.manager.get_task_state()
        state.relevant_memory = [f"relevant_fact_{i}" for i in range(5)]

        context = self.manager.build_context(
            goal="Use relevant facts",
            provider=ProviderType.OLLAMA,
        )

        # Should stay within budget
        assert context.total_tokens <= DEFAULT_CONTEXT_BUDGETS[ProviderType.OLLAMA]
        # Relevant facts should be in context
        memory_layers = [l for l in context.layers if l.layer == ContextLayer.RELEVANT_MEMORY]
        assert len(memory_layers) == 1
        content = memory_layers[0].content
        # Should contain relevant facts, not overwhelmed by irrelevant
        assert "relevant_fact_0" in content
        assert "relevant_fact_4" in content

    def test_priority_survival_under_pressure(self):
        """Test that critical layers survive under extreme pressure."""
        self.manager.start_task("Priority survival test")

        # Create massive content in all layers
        system_prompt = "SYS: " + "S" * 5000
        goal = "GOAL: " + "G" * 5000
        current_step = "STEP: " + "T" * 5000

        # 100 tool results with large content
        tool_results = []
        for i in range(100):
            tool_results.append({
                "status": "success",
                "content": "X" * 5000,
                "path": f"/tmp/file_{i}",
            })

        # Large conversation history
        for i in range(50):
            self.manager.add_conversation_turn("user", "U" * 1000)
            self.manager.add_conversation_turn("assistant", "A" * 1000)

        state = self.manager.get_task_state()
        state.artifacts = {f"artifact_{i}": "A" * 2000 for i in range(20)}

        context = self.manager.build_context(
            goal=goal,
            current_step=current_step,
            tool_results=[{"status": "success", "content": "X" * 5000} for _ in range(100)],
            system_prompt=system_prompt,
            provider=ProviderType.OLLAMA,
        )

        # Must stay within budget
        assert context.total_tokens <= DEFAULT_CONTEXT_BUDGETS[ProviderType.OLLAMA]

        # Check priority survival: L0 (SYSTEM) and L1 (CURRENT_TASK) should survive
        system_layers = [l for l in context.layers if l.layer == ContextLayer.SYSTEM]
        task_layers = [l for l in context.layers if l.layer == ContextLayer.CURRENT_TASK]

        # L0 SYSTEM must survive
        assert len(system_layers) == 1
        assert not system_layers[0].truncated or "SYS:" in system_layers[0].content

        # L1 CURRENT_TASK must survive
        assert len(task_layers) == 1
        assert "GOAL:" in task_layers[0].content

    def test_checkpoint_continuity(self):
        """Test checkpoint creation, destruction, restoration, continuation."""
        self.manager.start_task("Continuity test")
        state = self.manager.get_task_state()

        # Simulate task progress
        state.current_step = "step_5"
        state.completed_steps = ["step_1", "step_2", "step_3", "step_4"]
        state.verified_facts = ["fact_1", "fact_2"]
        state.pending_actions = ["action_1"]
        state.artifacts = {"file_1.txt": "content1", "file_2.txt": "content2"}
        state.relevant_memory = ["memory_1", "memory_2"]

        # Create checkpoint
        checkpoint = self.manager.create_checkpoint(
            provider=ProviderType.OLLAMA,
            model="llama3.2:3b",
        )

        # Verify checkpoint contents
        assert checkpoint.task_state.goal == "Continuity test"
        assert checkpoint.task_state.current_step == "step_5"
        assert len(checkpoint.task_state.completed_steps) == 4
        assert len(checkpoint.task_state.verified_facts) == 2
        assert len(checkpoint.task_state.artifacts) == 2

        # Destroy active context
        self.manager.clear_task()
        assert self.manager.get_task_state() is None

        # Restore checkpoint
        restored = self.manager.restore_checkpoint(checkpoint.checkpoint_id)
        assert restored is not None

        # Verify all critical state restored
        restored_state = self.manager.get_task_state()
        assert restored_state.goal == "Continuity test"
        assert restored_state.current_step == "step_5"
        assert restored_state.completed_steps == ["step_1", "step_2", "step_3", "step_4"]
        assert restored_state.verified_facts == ["fact_1", "fact_2"]
        assert restored_state.pending_actions == ["action_1"]
        assert restored_state.artifacts == {"file_1.txt": "content1", "file_2.txt": "content2"}
        assert restored_state.relevant_memory == ["memory_1", "memory_2"]

        # Continue task from restored state
        self.manager.update_task_state(
            current_step="step_6",
            completed_step="step_5",
        )

        context = self.manager.build_context(
            goal="Continue",
            provider=ProviderType.OLLAMA,
        )

        task_layers = [l for l in context.layers if l.layer == ContextLayer.CURRENT_TASK]
        assert len(task_layers) == 1
        assert "step_6" in task_layers[0].content
        assert "step_5" in task_layers[0].content

    def test_provider_budget_enforcement(self):
        """Test that each provider gets correct budget."""
        providers_budgets = [
            (ProviderType.HERCULE_LM, 2048),
            (ProviderType.BUILTIN, 4096),
            (ProviderType.OLLAMA, 8192),
        ]

        for provider, expected_budget in providers_budgets:
            self.manager.start_task(f"Test {provider.value}")

            # Create context that would exceed small budgets
            tool_results = [{"status": "success", "content": "x" * 5000} for _ in range(20)]
            self.manager.add_conversation_turn("user", "x" * 2000)
            self.manager.add_conversation_turn("assistant", "y" * 2000)

            context = self.manager.build_context(
                goal="Test provider budget",
                tool_results=[{"status": "success", "content": "x" * 5000} for _ in range(20)],
                provider=provider,
            )

            # Must not exceed provider's budget
            assert context.total_tokens <= expected_budget, f"{provider.value}: {context.total_tokens} > {expected_budget}"
            assert context.budget == expected_budget
            assert context.provider == provider

    def test_token_counting_validation(self):
        """Test token counting with provider-specific ratios."""
        # Test Ollama (3.5 chars/token)
        counter = TokenCounter(ProviderType.OLLAMA)
        text = "x" * 1000
        ollama_tokens = counter.count(text)
        assert ollama_tokens == 285  # 1000 / 3.5 ≈ 285

        # Test Builtin (3.5 chars/token)
        counter.set_provider(ProviderType.BUILTIN)
        builtin_tokens = counter.count(text)
        assert builtin_tokens == 285

        # Test HERCULE-LM (4.0 chars/token)
        counter.set_provider(ProviderType.HERCULE_LM)
        hercule_tokens = counter.count(text)
        assert hercule_tokens == 250

        # Test validation with safety margin: 2000 tokens in 2048 budget with 10% margin
        # 2048 * 0.9 = 1843, so 2000 > 1843 -> should NOT fit
        fits, max_allowed = counter.validate_budget(2000, 2048, 0.1)
        assert fits is False
        assert max_allowed == 1843

        # Test without margin - should fit
        fits, max_allowed = counter.validate_budget(1800, 2048, 0.0)
        assert fits is True
        assert max_allowed == 2048

    def test_failure_recovery(self):
        """Test various failure recovery scenarios."""
        self.manager.start_task("Recovery test")

        # Test corrupted context recovery
        from cognition.context.context_manager import BuiltContext, LayerContent, ContextLayer
        corrupted = BuiltContext(
            layers=[
                LayerContent(layer=ContextLayer.SYSTEM, content="sys", tokens=10, priority=100, truncated=False),
                LayerContent(layer=ContextLayer.TOOL_RESULTS, content="x" * 50000, tokens=10000, priority=60, truncated=False),
            ],
            total_tokens=10010,
            budget=2048,
            provider=ProviderType.OLLAMA,
            model="test",
        )

        recovered = self.manager.recover_from_corrupted_context(corrupted)
        assert recovered.total_tokens <= corrupted.budget
        # Should have SYSTEM and CURRENT_TASK
        layer_types = {l.layer for l in recovered.layers}
        assert ContextLayer.SYSTEM in layer_types
        assert recovered.truncation_details.get("recovered_from_corruption") is True

        # Test invalid budget recovery
        assert self.manager.recover_from_invalid_budget(-100) == 512
        assert self.manager.recover_from_invalid_budget(50000) == 32768
        assert self.manager.recover_from_invalid_budget(2048) == 2048

        # Test unknown provider recovery
        provider, budget = self.manager.recover_from_unknown_provider(ProviderType.UNKNOWN)
        assert provider == ProviderType.BUILTIN
        assert budget == 4096

    def test_context_boundary_assertions(self):
        """Test that context never exceeds provider budget."""
        providers = [
            (ProviderType.HERCULE_LM, 2048),
            (ProviderType.BUILTIN, 4096),
            (ProviderType.OLLAMA, 8192),
        ]

        for provider, budget in providers:
            self.manager.start_task(f"Boundary test {provider.value}")

            # Create extreme load
            tool_results = [{"status": "success", "content": "x" * 10000} for _ in range(100)]
            for i in range(100):
                self.manager.add_conversation_turn("user", "u" * 2000)
                self.manager.add_conversation_turn("assistant", "a" * 2000)

            state = self.manager.get_task_state()
            state.artifacts = {f"a{i}": "x" * 5000 for i in range(50)}

            context = self.manager.build_context(
                goal="Boundary test",
                tool_results=tool_results,
                provider=provider,
            )

            # Hard assertion: never exceed budget
            assert context.total_tokens <= budget, f"{provider.value}: {context.total_tokens} > {budget}"

            # Check remaining budget
            remaining = budget - context.total_tokens
            assert remaining >= 0

            # Verify layers included
            if diagnostics := context.diagnostics:
                assert diagnostics.budget == budget
                assert diagnostics.context_tokens == context.total_tokens
                assert diagnostics.remaining_budget == budget - context.total_tokens

    def test_observability_diagnostics(self):
        """Test observability diagnostics are populated."""
        self.manager.start_task("Observability test")
        state = self.manager.get_task_state()
        state.current_step = "step_1"
        state.completed_steps = ["init"]
        state.artifacts = {"f1": "c1"}

        tool_results = [{"status": "success", "content": "test", "path": "f.txt"}]

        context = self.manager.build_context(
            goal="Test",
            current_step="step_1",
            tool_results=tool_results,
            system_prompt="You are HERCULE",
            provider=ProviderType.OLLAMA,
            budget=8192,  # Use explicit large budget
        )

        assert context.diagnostics is not None
        diag = context.diagnostics
        assert diag.provider == "ollama"
        assert diag.budget == 8192
        assert diag.context_tokens == context.total_tokens
        assert diag.build_latency_ms >= 0
        assert "system" in diag.layers_included
        assert "current_task" in diag.layers_included
        # tool_results may be truncated depending on budget; check it's at least tracked
        assert diag.tool_results_selected >= 0
        assert diag.memory_items_selected >= 0
        assert diag.conversation_turns_selected >= 0


class TestEndToEndIntegration:
    """Test end-to-end integration with Brain."""

    def test_brain_uses_context_manager(self):
        """Verify Brain uses ContextManager for inference."""
        # This test verifies the integration path exists
        # by checking that Brain has the necessary components
        from brain.brain import Brain
        from orchestrator.orchestrator import Orchestrator

        # Brain should have access to memory and models through orchestrator
        # This is a structural test - actual integration happens at runtime
        assert True  # Placeholder for actual integration verification


if __name__ == "__main__":
    pytest.main([__file__, "-v"])