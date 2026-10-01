"""Tests for Context Management."""

from __future__ import annotations

import pytest
from cognition.context.context_manager import (
    ContextManager,
    ContextBuilder,
    ContextLayer,
    ProviderType,
    LayerContent,
    StructuredTaskState,
    ContextCheckpoint,
    BuiltContext,
    TokenCounter,
    ToolOutputNormalizer,
    DEFAULT_CONTEXT_BUDGETS,
    LAYER_PRIORITY,
    LAYER_MAX_TOKENS,
    create_context_manager,
)
from memory.memory_manager import MemoryManager
from models.model_manager import ModelManager


class TestTokenCounter:
    """Tests for TokenCounter."""

    def test_count_empty(self):
        counter = TokenCounter()
        assert counter.count("") == 0

    def test_count_simple(self):
        # "hello world" = 11 chars ≈ 2-3 tokens
        counter = TokenCounter()
        assert counter.count("hello world") >= 2

    def test_count_long(self):
        counter = TokenCounter()
        text = "x" * 1000
        assert counter.count(text) == 250  # 1000/4

    def test_count_messages(self):
        counter = TokenCounter()
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "world"},
        ]
        tokens = counter.count_messages(messages)
        assert tokens > 0


class TestToolOutputNormalizer:
    """Tests for ToolOutputNormalizer."""

    def test_normalize_none(self):
        assert ToolOutputNormalizer.normalize(None) == ""

    def test_normalize_string(self):
        result = ToolOutputNormalizer.normalize("simple string", max_tokens=10)
        assert "simple string" in result

    def test_normalize_long_string(self):
        long_str = "x" * 1000
        result = ToolOutputNormalizer.normalize(long_str, max_tokens=10)
        assert len(result) <= 50  # truncated

    def test_normalize_dict_success(self):
        result = ToolOutputNormalizer.normalize({
            "status": "success",
            "content": "file created",
            "path": "/tmp/test.txt",
        }, max_tokens=50)
        assert "success" in result
        assert "file created" in result
        assert "/tmp/test.txt" in result

    def test_normalize_dict_error(self):
        result = ToolOutputNormalizer.normalize({
            "status": "failed",
            "error": "permission denied",
        }, max_tokens=50)
        assert "failed" in result
        assert "permission denied" in result

    def test_normalize_list(self):
        result = ToolOutputNormalizer.normalize(["a", "b", "c"], max_tokens=50)
        assert "a" in result
        assert "b" in result
        assert "c" in result


class TestStructuredTaskState:
    """Tests for StructuredTaskState."""

    def test_create_basic(self):
        state = StructuredTaskState(goal="test goal")
        assert state.goal == "test goal"
        assert state.checkpoint_id != ""

    def test_updates(self):
        state = StructuredTaskState(goal="test")
        state.current_step = "step1"
        state.completed_steps.append("step1")
        state.failed_steps.append("step2")
        state.verified_facts.append("fact1")
        state.pending_actions.append("action1")
        state.artifacts["file"] = "content"
        state.capability_states["FILE_READ"] = {"status": "verified"}

        assert state.current_step == "step1"
        assert "step1" in state.completed_steps
        assert "step2" in state.failed_steps
        assert "fact1" in state.verified_facts
        assert "action1" in state.pending_actions
        assert state.artifacts["file"] == "content"
        assert state.capability_states["FILE_READ"]["status"] == "verified"


class TestContextBuilder:
    """Tests for ContextBuilder."""

    def setup_method(self):
        self.memory = MemoryManager()
        self.models = ModelManager()
        self.builder = ContextBuilder(self.memory, self.models)

    def test_build_basic(self):
        context = self.builder.build(
            goal="Create a test file",
            current_step="write_file",
            system_prompt="You are HERCULE",
            provider=ProviderType.OLLAMA,
            model="llama3.2:3b",
        )
        assert isinstance(context, BuiltContext)
        assert context.total_tokens > 0
        assert context.budget == DEFAULT_CONTEXT_BUDGETS[ProviderType.OLLAMA]
        assert context.provider == ProviderType.OLLAMA

    def test_build_with_task_state(self):
        task_state = StructuredTaskState(
            goal="Create test file",
            current_step="write_file",
            completed_steps=["plan"],
            verified_facts=["workspace selected"],
        )
        context = self.builder.build(
            goal="Create test file",
            current_step="write_file",
            task_state=task_state,
            provider=ProviderType.BUILTIN,
        )
        assert context.total_tokens > 0
        # Should have task layer with completed steps
        task_layer = next((l for l in context.layers if l.layer == ContextLayer.CURRENT_TASK), None)
        assert task_layer is not None
        assert "plan" in task_layer.content.lower() or "COMPLETED" in task_layer.content

    def test_build_with_tool_results(self):
        tool_results = [
            {"status": "success", "content": "file created", "path": "test.txt"},
            {"status": "failed", "error": "permission denied"},
        ]
        context = self.builder.build(
            goal="Test",
            tool_results=tool_results,
            provider=ProviderType.HERCULE_LM,
        )
        tool_layer = next((l for l in context.layers if l.layer == ContextLayer.TOOL_RESULTS), None)
        assert tool_layer is not None
        assert "success" in tool_layer.content or "failed" in tool_layer.content

    def test_build_with_verification(self):
        verification = {
            "passed_steps": 3,
            "failed_steps": 1,
            "capability_states": {
                "FILE_READ": {"verification": {"passed": True}},
                "FILE_WRITE": {"verification": {"passed": False}},
            },
        }
        context = self.builder.build(
            goal="Test",
            verification_state=verification,
            provider=ProviderType.OLLAMA,
        )
        verify_layer = next((l for l in context.layers if l.layer == ContextLayer.VERIFICATION_STATE), None)
        assert verify_layer is not None
        assert "3 passed" in verify_layer.content
        assert "1 failed" in verify_layer.content

    def test_build_with_conversation(self):
        conversation = [
            {"role": "user", "content": "Create a file"},
            {"role": "assistant", "content": "Created file.txt"},
            {"role": "user", "content": "Now edit it"},
            {"role": "assistant", "content": "Edited file.txt"},
        ]
        context = self.builder.build(
            goal="Test",
            conversation_history=conversation,
            provider=ProviderType.OLLAMA,
        )
        conv_layer = next((l for l in context.layers if l.layer == ContextLayer.CONVERSATION), None)
        assert conv_layer is not None
        assert "user" in conv_layer.content
        assert "assistant" in conv_layer.content

    def test_budget_enforcement(self):
        # Very small budget should truncate
        context = self.builder.build(
            goal="Test goal with very long description " + "x" * 1000,
            system_prompt="System prompt " + "y" * 1000,
            provider=ProviderType.HERCULE_LM,  # 2048 budget
            budget=100,  # Very small
        )
        assert context.total_tokens <= 100
        assert context.truncated is True

    def test_to_prompt(self):
        context = self.builder.build(
            goal="Test",
            provider=ProviderType.OLLAMA,
        )
        prompt = context.to_prompt()
        assert "GOAL: Test" in prompt


class TestContextManager:
    """Tests for ContextManager."""

    def setup_method(self):
        self.memory = MemoryManager()
        self.models = ModelManager()
        self.manager = ContextManager(self.memory, self.models)

    def test_start_task(self):
        state = self.manager.start_task("Create a test file")
        assert state.goal == "Create a test file"
        assert state.current_step == ""
        assert state.checkpoint_id != ""

    def test_update_task_state(self):
        self.manager.start_task("Test goal")
        state = self.manager.update_task_state(
            current_step="step1",
            completed_step="step0",
            verified_fact="workspace ready",
            pending_action="write file",
            artifact=("file1.txt", "content1"),
            capability_state=("FILE_READ", {"status": "verified"}),
        )
        assert state.current_step == "step1"
        assert "step0" in state.completed_steps
        assert "workspace ready" in state.verified_facts
        assert "write file" in state.pending_actions
        assert state.artifacts["file1.txt"] == "content1"
        assert state.capability_states["FILE_READ"]["status"] == "verified"

    def test_build_context_with_task(self):
        self.manager.start_task("Create test file")
        self.manager.update_task_state(current_step="write", completed_step="plan")
        context = self.manager.build_context(
            goal="Create test file",
            provider=ProviderType.OLLAMA,
        )
        assert context.total_tokens > 0

    def test_conversation_history(self):
        self.manager.add_conversation_turn("user", "Hello")
        self.manager.add_conversation_turn("assistant", "Hi there")
        self.manager.add_conversation_turn("user", "Create file")
        context = self.manager.build_context(
            goal="Test",
            provider=ProviderType.OLLAMA,
        )
        conv_layer = next((l for l in context.layers if l.layer == ContextLayer.CONVERSATION), None)
        assert conv_layer is not None
        assert "user" in conv_layer.content
        assert "assistant" in conv_layer.content

    def test_checkpoint_create_restore(self):
        self.manager.start_task("Long running task")
        state = self.manager.update_task_state(
            current_step="step3",
        )
        state = self.manager.update_task_state(
            completed_step="step1",
        )
        state = self.manager.update_task_state(
            completed_step="step2",
        )
        checkpoint = self.manager.create_checkpoint(
            provider=ProviderType.OLLAMA,
            model="llama3.2:3b",
        )
        assert checkpoint.checkpoint_id != ""
        assert checkpoint.task_state.current_step == "step3"
        assert len(checkpoint.task_state.completed_steps) == 2

        # Clear and restore
        self.manager.clear_task()
        assert self.manager.get_task_state() is None

        restored = self.manager.restore_checkpoint(checkpoint.checkpoint_id)
        assert restored is not None
        assert restored.task_state.current_step == "step3"
        assert len(restored.task_state.completed_steps) == 2

    def test_checkpoint_list(self):
        self.manager.start_task("Task 1")
        cp1 = self.manager.create_checkpoint()
        self.manager.clear_task()

        self.manager.start_task("Task 2")
        cp2 = self.manager.create_checkpoint()

        checkpoints = self.manager.list_checkpoints()
        assert len(checkpoints) == 2
        assert any(c["checkpoint_id"] == cp1.checkpoint_id for c in checkpoints)
        assert any(c["checkpoint_id"] == cp2.checkpoint_id for c in checkpoints)

    def test_delete_checkpoint(self):
        self.manager.start_task("Task")
        cp = self.manager.create_checkpoint()
        assert self.manager.delete_checkpoint(cp.checkpoint_id) is True
        assert self.manager.delete_checkpoint("nonexistent") is False

    def test_compress_context(self):
        # Create a large context
        self.manager.start_task("Test")
        context = self.manager.build_context(
            goal="Test " + "x" * 1000,
            system_prompt="System " + "y" * 1000,
            provider=ProviderType.OLLAMA,
            budget=8192,
        )
        # Compress to smaller budget
        compressed = self.manager.compress_context(context, target_budget=500)
        assert compressed.total_tokens <= 500
        assert compressed.truncated is True

    def test_compact_conversation(self):
        # Add many turns
        for i in range(10):
            self.manager.add_conversation_turn("user", f"Message {i}")
            self.manager.add_conversation_turn("assistant", f"Response {i}")
        summary = self.manager.compact_conversation(keep_turns=4)
        assert "Previous conversation" in summary
        assert "16 turns" in summary  # 20 - 4 = 16 older turns

    def test_clear_task(self):
        self.manager.start_task("Test")
        self.manager.add_conversation_turn("user", "Hi")
        self.manager.clear_task()
        assert self.manager.get_task_state() is None
        assert len(self.manager._conversation_history) == 0


class TestProviderDetection:
    """Tests for provider detection."""

    def test_detect_ollama(self):
        memory = MemoryManager()
        models = ModelManager()
        manager = ContextManager(memory, models)

        assert manager._detect_provider("llama3.2:3b") == ProviderType.OLLAMA
        assert manager._detect_provider("qwen2.5:1.5b") == ProviderType.OLLAMA
        assert manager._detect_provider("mistral:7b") == ProviderType.OLLAMA

    def test_detect_builtin(self):
        memory = MemoryManager()
        models = ModelManager()
        manager = ContextManager(memory, models)

        assert manager._detect_provider("hercule-local") == ProviderType.BUILTIN
        assert manager._detect_provider("builtin-model") == ProviderType.BUILTIN

    def test_detect_hercule_lm(self):
        memory = MemoryManager()
        models = ModelManager()
        manager = ContextManager(memory, models)

        assert manager._detect_provider("hercule-lm-micro") == ProviderType.HERCULE_LM
        assert manager._detect_provider("hercule-lm-nano") == ProviderType.HERCULE_LM

    def test_detect_mock(self):
        memory = MemoryManager()
        models = ModelManager()
        manager = ContextManager(memory, models)

        assert manager._detect_provider("mock") == ProviderType.MOCK

    def test_detect_unknown(self):
        memory = MemoryManager()
        models = ModelManager()
        manager = ContextManager(memory, models)

        assert manager._detect_provider("unknown-model") == ProviderType.UNKNOWN
        assert manager._detect_provider("") == ProviderType.UNKNOWN


class TestLayerConstants:
    """Tests for layer constants and defaults."""

    def test_default_budgets(self):
        assert ProviderType.OLLAMA in DEFAULT_CONTEXT_BUDGETS
        assert ProviderType.BUILTIN in DEFAULT_CONTEXT_BUDGETS
        assert ProviderType.HERCULE_LM in DEFAULT_CONTEXT_BUDGETS
        assert DEFAULT_CONTEXT_BUDGETS[ProviderType.OLLAMA] == 8192
        assert DEFAULT_CONTEXT_BUDGETS[ProviderType.BUILTIN] == 4096
        assert DEFAULT_CONTEXT_BUDGETS[ProviderType.HERCULE_LM] == 2048

    def test_layer_priority_order(self):
        # SYSTEM should be highest priority
        assert LAYER_PRIORITY[ContextLayer.SYSTEM] > LAYER_PRIORITY[ContextLayer.CURRENT_TASK]
        assert LAYER_PRIORITY[ContextLayer.CURRENT_TASK] > LAYER_PRIORITY[ContextLayer.ACTIVE_STATE]
        assert LAYER_PRIORITY[ContextLayer.ACTIVE_STATE] > LAYER_PRIORITY[ContextLayer.RELEVANT_MEMORY]
        assert LAYER_PRIORITY[ContextLayer.RELEVANT_MEMORY] > LAYER_PRIORITY[ContextLayer.TOOL_RESULTS]
        assert LAYER_PRIORITY[ContextLayer.TOOL_RESULTS] > LAYER_PRIORITY[ContextLayer.VERIFICATION_STATE]
        assert LAYER_PRIORITY[ContextLayer.VERIFICATION_STATE] > LAYER_PRIORITY[ContextLayer.CONVERSATION]

    def test_layer_max_tokens(self):
        for layer in ContextLayer:
            assert layer in LAYER_MAX_TOKENS
            assert LAYER_MAX_TOKENS[layer] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])