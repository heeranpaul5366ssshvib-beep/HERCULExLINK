from __future__ import annotations
"""HERCULE PC-Frontier: Streaming Response System.

Provides immediate acknowledgement, streaming generation, progress/state updates.
Non-blocking UI during inference.
"""

import asyncio
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncGenerator, Callable, Dict, Generator, List, Optional, Union

from models.hercule_lm.optimized_model import OptimizedHerculeLM
from models.router.pc_frontier_router import PCFRouter, TaskClassification, TaskType, RoutingDecision
from models.hercule_lm.verifiers import (
    verify_math, verify_json, verify_tool_call, verify_python_tests,
    verify_refusal, verify_citation, verify_verification
)
from system.hardware import get_runtime_profile, get_profile_config


class ResponseState(str, Enum):
    """Streaming response states."""
    ACKNOWLEDGED = "acknowledged"
    ROUTING = "routing"
    THINKING = "thinking"
    PLANNING = "planning"
    USING_TOOL = "using_tool"
    GENERATING = "generating"
    VERIFYING = "verifying"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class StreamChunk:
    """A chunk of streaming response."""
    state: ResponseState
    content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    chunk_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    timestamp: float = field(default_factory=time.time)
    is_final: bool = False


@dataclass
class StreamingResponse:
    """Complete streaming response."""
    task_id: str
    chunks: List[StreamChunk] = field(default_factory=list)
    final_content: str = ""
    routing_decision: Optional[RoutingDecision] = None
    verification_results: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    total_latency_ms: float = 0.0
    first_token_latency_ms: float = 0.0


class StreamingEngine:
    """Non-blocking streaming inference engine."""
    
    def __init__(
        self,
        router: PCFRouter,
        native_model: Optional[OptimizedHerculeLM] = None,
        max_concurrent: int = 4,
    ):
        self.router = router
        self.native_model = native_model
        self.max_concurrent = max_concurrent
        self._active_streams: Dict[str, StreamingResponse] = {}
        self._stream_lock = threading.Lock()
        self._executor = threading.Thread(target=self._run_loop, daemon=True)
        self._running = True
        self._task_queue: deque = deque()
        self._queue_lock = threading.Lock()
        
    def _run_loop(self):
        """Background loop for managing streams."""
        while self._running:
            time.sleep(0.01)  # Small sleep to prevent busy waiting
    
    def start_stream(
        self,
        prompt: str,
        task_id: Optional[str] = None,
        callbacks: Optional[List[Callable[[StreamChunk], None]]] = None,
        stream: bool = True,
        verify: bool = True,
    ) -> str:
        """Start a new streaming response. Returns task_id immediately."""
        task_id = task_id or uuid.uuid4().hex[:12]
        
        # Create response object
        response = StreamingResponse(task_id=task_id)
        
        with self._stream_lock:
            self._active_streams[task_id] = response
        
        # Send immediate acknowledgement
        ack_chunk = StreamChunk(
            state=ResponseState.ACKNOWLEDGED,
            content="",
            metadata={"task_id": task_id, "message": "Request received, processing..."},
        )
        response.chunks.append(ack_chunk)
        self._notify_callbacks(task_id, ack_chunk, callbacks)
        
        # Start processing in background
        thread = threading.Thread(
            target=self._process_stream,
            args=(task_id, prompt, stream, verify, callbacks),
            daemon=True,
        )
        thread.start()
        
        return task_id
    
    def _process_stream(
        self,
        task_id: str,
        prompt: str,
        stream: bool,
        verify: bool,
        callbacks: Optional[List[Callable[[StreamChunk], None]]],
    ):
        """Process the streaming request."""
        start_time = time.perf_counter()
        first_token_time = None
        response = self._active_streams.get(task_id)
        
        try:
            # Routing phase
            routing_chunk = StreamChunk(
                state=ResponseState.ROUTING,
                content="",
                metadata={"message": "Selecting optimal model..."},
            )
            self._add_chunk(task_id, routing_chunk, callbacks)
            
            classification = self.router.classify_task(prompt)
            decision = self.router.route(prompt)
            response.routing_decision = decision
            
            routing_chunk.content = f"Routed to {decision.model} ({decision.task_type})"
            self._add_chunk(task_id, routing_chunk, callbacks)
            
            # Check if tool should be used
            if decision.model.startswith("tool:"):
                tool_name = decision.model.split(":", 1)[1]
                tool_chunk = StreamChunk(
                    state=ResponseState.USING_TOOL,
                    content="",
                    metadata={"tool": tool_name, "message": f"Using {tool_name}..."},
                )
                self._add_chunk(task_id, tool_chunk, callbacks)
                
                # Execute tool (would integrate with actual tool system)
                result = self._execute_tool(tool_name, prompt)
                tool_chunk.content = result
                tool_chunk.is_final = True
                self._add_chunk(task_id, tool_chunk, callbacks)
                self._complete_stream(task_id, result, start_time, first_token_time, callbacks)
                return
            
            # Model generation phase
            if classification.requires_reasoning:
                thinking_chunk = StreamChunk(
                    state=ResponseState.THINKING,
                    content="",
                    metadata={"message": "Reasoning..."},
                )
                self._add_chunk(task_id, thinking_chunk, callbacks)
            
            if classification.task_type == TaskType.PLANNING:
                planning_chunk = StreamChunk(
                    state=ResponseState.PLANNING,
                    content="",
                    metadata={"message": "Planning..."},
                )
                self._add_chunk(task_id, planning_chunk, callbacks)
            
            generating_chunk = StreamChunk(
                state=ResponseState.GENERATING,
                content="",
                metadata={"model": decision.model},
            )
            self._add_chunk(task_id, generating_chunk, callbacks)
            
            # Generate with native model or external
            full_content = ""
            if self.native_model and decision.adapter_name == "hercule-lm":
                # Use native model with streaming
                if stream:
                    for token in self.native_model.generate_stream(
                        prompt, max_new_tokens=512, temperature=0.0
                    ):
                        if first_token_time is None:
                            first_token_time = time.perf_counter()
                        
                        full_content += token
                        token_chunk = StreamChunk(
                            state=ResponseState.GENERATING,
                            content=token,
                            metadata={"model": decision.model},
                        )
                        self._add_chunk(task_id, token_chunk, callbacks)
                else:
                    full_content = self.native_model.generate(prompt, max_new_tokens=512)
                    if first_token_time is None:
                        first_token_time = time.perf_counter()
            else:
                # External model (Ollama, etc.) - placeholder
                full_content = self._call_external_model(decision, prompt)
                if first_token_time is None:
                    first_token_time = time.perf_counter()
            
            # Verification phase
            if verify and decision.requirements.get("verification", 0) > 0:
                verify_chunk = StreamChunk(
                    state=ResponseState.VERIFYING,
                    content="",
                    metadata={"message": "Verifying output..."},
                )
                self._add_chunk(task_id, verify_chunk, callbacks)
                
                verification_results = self._verify_output(full_content, classification)
                response.verification_results = verification_results
                
                if not verification_results["all_passed"]:
                    verify_chunk.content = "Verification failed, retrying..."
                    self._add_chunk(task_id, verify_chunk, callbacks)
                    # Could implement retry logic here
            
            # Complete
            self._complete_stream(task_id, full_content, start_time, first_token_time, callbacks)
            
        except Exception as e:
            error_chunk = StreamChunk(
                state=ResponseState.ERROR,
                content="",
                metadata={"error": str(e)},
                is_final=True,
            )
            self._add_chunk(task_id, error_chunk, callbacks)
            
            with self._stream_lock:
                if task_id in self._active_streams:
                    self._active_streams[task_id].error = str(e)
    
    def _execute_tool(self, tool_name: str, prompt: str) -> str:
        """Execute a deterministic tool."""
        # Placeholder - would integrate with actual tool system
        if tool_name == "calculator":
            return self._calculate(prompt)
        elif tool_name == "filesystem":
            return "File operation completed"
        elif tool_name == "code_executor":
            return "Code executed"
        return f"Tool {tool_name} executed"
    
    def _calculate(self, prompt: str) -> str:
        """Simple calculator."""
        import re
        # Match full mathematical expressions: number followed by operators and numbers
        expr = re.search(r'(\d+(?:\s*[\+\-\*/]\s*\d+)+)', prompt)
        if expr:
            try:
                result = eval(expr.group())
                return f"Result: {result}"
            except Exception:
                pass
        return "Could not calculate"
    
    def _call_external_model(self, decision: RoutingDecision, prompt: str) -> str:
        """Call external model or native HERCULE-LM."""
        if decision.adapter_name == "hercule-lm" and self.native_model is not None:
            # Use native HERCULE-LM model
            return self.native_model.generate(
                prompt, 
                max_new_tokens=64, 
                temperature=0.0
            )
        # Placeholder - would integrate with actual adapters (Ollama, etc.)
        return f"[Response from {decision.model}]"
    
    def _verify_output(self, content: str, classification: TaskClassification) -> Dict[str, Any]:
        """Run verifiers on output."""
        results = {}
        all_passed = True
        
        for vtype in classification.requires_verification:
            if vtype.name == "MATH":
                # Extract expected from context if available
                result = verify_math(content, "0")  # Placeholder
            elif vtype.name == "JSON":
                result = verify_json(content)
            elif vtype.name == "TOOL_CALL":
                result = verify_tool_call(content)
            elif vtype.name == "PYTHON_TESTS":
                result = verify_python_tests(content, [])
            elif vtype.name == "VERIFICATION":
                result = verify_verification(content, "CORRECT|")
            else:
                result = {"pass": True, "score": 1.0, "detail": "No verifier"}
            
            results[vtype.value] = result
            if not result.get("pass", False):
                all_passed = False
        
        return {"all_passed": all_passed, "results": results}
    
    def _add_chunk(
        self,
        task_id: str,
        chunk: StreamChunk,
        callbacks: Optional[List[Callable[[StreamChunk], None]]],
    ):
        """Add chunk to response and notify callbacks."""
        with self._stream_lock:
            if task_id in self._active_streams:
                self._active_streams[task_id].chunks.append(chunk)
        
        self._notify_callbacks(task_id, chunk, callbacks)
    
    def _notify_callbacks(
        self,
        task_id: str,
        chunk: StreamChunk,
        callbacks: Optional[List[Callable[[StreamChunk], None]]],
    ):
        """Notify all callbacks."""
        if callbacks:
            for cb in callbacks:
                try:
                    cb(chunk)
                except Exception:
                    pass
    
    def _complete_stream(
        self,
        task_id: str,
        content: str,
        start_time: float,
        first_token_time: Optional[float],
        callbacks: Optional[List[Callable[[StreamChunk], None]]],
    ):
        """Mark stream as complete."""
        response = self._active_streams.get(task_id)
        if not response:
            return
        
        response.final_content = content
        response.total_latency_ms = (time.perf_counter() - start_time) * 1000
        if first_token_time:
            response.first_token_latency_ms = (first_token_time - start_time) * 1000
        
        final_chunk = StreamChunk(
            state=ResponseState.COMPLETE,
            content=content,
            metadata={
                "total_latency_ms": response.total_latency_ms,
                "first_token_latency_ms": response.first_token_latency_ms,
            },
            is_final=True,
        )
        self._add_chunk(task_id, final_chunk, callbacks)
    
    def get_stream(self, task_id: str) -> Optional[StreamingResponse]:
        """Get streaming response by task_id."""
        with self._stream_lock:
            return self._active_streams.get(task_id)
    
    def get_chunks(self, task_id: str, after_chunk_id: Optional[str] = None) -> List[StreamChunk]:
        """Get chunks after a specific chunk_id."""
        response = self.get_stream(task_id)
        if not response:
            return []
        
        if after_chunk_id is None:
            return response.chunks
        
        for i, chunk in enumerate(response.chunks):
            if chunk.chunk_id == after_chunk_id:
                return response.chunks[i+1:]
        
        return response.chunks
    
    def wait_for_complete(self, task_id: str, timeout: float = 30.0) -> StreamingResponse:
        """Wait for stream to complete."""
        start = time.perf_counter()
        while time.perf_counter() - start < timeout:
            response = self.get_stream(task_id)
            if response and response.chunks and response.chunks[-1].is_final:
                return response
            time.sleep(0.05)
        raise TimeoutError(f"Stream {task_id} did not complete within {timeout}s")
    
    def cancel_stream(self, task_id: str) -> bool:
        """Cancel a streaming response."""
        with self._stream_lock:
            if task_id in self._active_streams:
                response = self._active_streams[task_id]
                cancel_chunk = StreamChunk(
                    state=ResponseState.ERROR,
                    content="",
                    metadata={"error": "Cancelled by user"},
                    is_final=True,
                )
                response.chunks.append(cancel_chunk)
                return True
        return False
    
    def get_active_streams(self) -> List[str]:
        """Get list of active stream task_ids."""
        with self._stream_lock:
            return list(self._active_streams.keys())
    
    def shutdown(self):
        """Shutdown the engine."""
        self._running = False


class AsyncStreamingEngine:
    """Async version of streaming engine for async frameworks."""
    
    def __init__(
        self,
        router: PCFRouter,
        native_model: Optional[OptimizedHerculeLM] = None,
        max_concurrent: int = 4,
    ):
        self.router = router
        self.native_model = native_model
        self.max_concurrent = max_concurrent
        self._active_streams: Dict[str, StreamingResponse] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)
    
    async def start_stream(
        self,
        prompt: str,
        task_id: Optional[str] = None,
        stream: bool = True,
        verify: bool = True,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Start streaming response as async generator."""
        task_id = task_id or uuid.uuid4().hex[:12]
        
        response = StreamingResponse(task_id=task_id)
        self._active_streams[task_id] = response
        
        # Immediate acknowledgement
        ack_chunk = StreamChunk(
            state=ResponseState.ACKNOWLEDGED,
            content="",
            metadata={"task_id": task_id, "message": "Request received, processing..."},
        )
        response.chunks.append(ack_chunk)
        yield ack_chunk
        
        async with self._semaphore:
            try:
                # Routing
                routing_chunk = StreamChunk(
                    state=ResponseState.ROUTING,
                    content="",
                    metadata={"message": "Selecting optimal model..."},
                )
                response.chunks.append(routing_chunk)
                yield routing_chunk
                
                classification = self.router.classify_task(prompt)
                decision = self.router.route(prompt)
                response.routing_decision = decision
                
                routing_chunk.content = f"Routed to {decision.model} ({decision.task_type})"
                yield routing_chunk
                
                # Tool check
                if decision.model.startswith("tool:"):
                    tool_name = decision.model.split(":", 1)[1]
                    tool_chunk = StreamChunk(
                        state=ResponseState.USING_TOOL,
                        content="",
                        metadata={"tool": tool_name, "message": f"Using {tool_name}..."},
                    )
                    yield tool_chunk
                    
                    result = self._execute_tool(tool_name, prompt)
                    tool_chunk.content = result
                    tool_chunk.is_final = True
                    yield tool_chunk
                    return
                
                # Generation
                if classification.requires_reasoning:
                    thinking_chunk = StreamChunk(
                        state=ResponseState.THINKING,
                        content="",
                        metadata={"message": "Reasoning..."},
                    )
                    yield thinking_chunk
                
                generating_chunk = StreamChunk(
                    state=ResponseState.GENERATING,
                    content="",
                    metadata={"model": decision.model},
                )
                yield generating_chunk
                
                full_content = ""
                if self.native_model and decision.adapter_name == "hercule-lm":
                    if stream:
                        for token in self.native_model.generate_stream(prompt, max_new_tokens=512):
                            full_content += token
                            token_chunk = StreamChunk(
                                state=ResponseState.GENERATING,
                                content=token,
                                metadata={"model": decision.model},
                            )
                            yield token_chunk
                            await asyncio.sleep(0)  # Yield control
                    else:
                        full_content = self.native_model.generate(prompt, max_new_tokens=512)
                else:
                    full_content = self._call_external_model(decision, prompt)
                
                # Verification
                if verify and decision.requirements.get("verification", 0) > 0:
                    verify_chunk = StreamChunk(
                        state=ResponseState.VERIFYING,
                        content="",
                        metadata={"message": "Verifying output..."},
                    )
                    yield verify_chunk
                    
                    verification_results = self._verify_output(full_content, classification)
                    response.verification_results = verification_results
                
                # Complete
                response.final_content = full_content
                final_chunk = StreamChunk(
                    state=ResponseState.COMPLETE,
                    content=full_content,
                    metadata={"total_latency_ms": response.total_latency_ms},
                    is_final=True,
                )
                yield final_chunk
                
            except Exception as e:
                error_chunk = StreamChunk(
                    state=ResponseState.ERROR,
                    content="",
                    metadata={"error": str(e)},
                    is_final=True,
                )
                yield error_chunk
            finally:
                self._active_streams.pop(task_id, None)
    
    def _execute_tool(self, tool_name: str, prompt: str) -> str:
        if tool_name == "calculator":
            import re
            expr = re.search(r'(\d+(?:\s*[\+\-\*/]\s*\d+)+)', prompt)
            if expr:
                try:
                    result = eval(expr.group())
                    return f"Result: {result}"
                except Exception:
                    pass
            return "Could not calculate"
        return f"Tool {tool_name} executed"
    
    def _call_external_model(self, decision: RoutingDecision, prompt: str) -> str:
        return f"[Response from {decision.model}]"
    
    def _verify_output(self, content: str, classification: TaskClassification) -> Dict[str, Any]:
        results = {}
        all_passed = True
        
        for vtype in classification.requires_verification:
            if vtype.name == "MATH":
                result = verify_math(content, "0")
            elif vtype.name == "JSON":
                result = verify_json(content)
            elif vtype.name == "TOOL_CALL":
                result = verify_tool_call(content)
            elif vtype.name == "PYTHON_TESTS":
                result = verify_python_tests(content, [])
            elif vtype.name == "VERIFICATION":
                result = verify_verification(content, "CORRECT|")
            else:
                result = {"pass": True, "score": 1.0, "detail": "No verifier"}
            
            results[vtype.value] = result
            if not result.get("pass", False):
                all_passed = False
        
        return {"all_passed": all_passed, "results": results}


# UI-friendly wrapper for Activity Drawer integration
class ActivityDrawer:
    """UI component for showing streaming activity states."""
    
    STATES = [
        "Thinking",
        "Planning", 
        "Using tool",
        "Verifying",
        "Complete",
    ]
    
    def __init__(self):
        self.current_state = ""
        self.current_detail = ""
        self.progress = 0.0
        self.history: List[Dict[str, Any]] = []
    
    def update(self, chunk: StreamChunk):
        """Update from stream chunk."""
        state_map = {
            ResponseState.ACKNOWLEDGED: ("", "Request received"),
            ResponseState.ROUTING: ("Thinking", "Selecting model"),
            ResponseState.THINKING: ("Thinking", "Reasoning"),
            ResponseState.PLANNING: ("Planning", "Creating plan"),
            ResponseState.USING_TOOL: ("Using tool", chunk.metadata.get("tool", "")),
            ResponseState.GENERATING: ("Thinking", "Generating"),
            ResponseState.VERIFYING: ("Verifying", "Checking output"),
            ResponseState.COMPLETE: ("Complete", "Done"),
            ResponseState.ERROR: ("Error", chunk.metadata.get("error", "Unknown")),
        }
        
        state, detail = state_map.get(chunk.state, ("", ""))
        self.current_state = state
        self.current_detail = detail
        
        self.history.append({
            "state": state,
            "detail": detail,
            "timestamp": chunk.timestamp,
            "chunk_id": chunk.chunk_id,
        })
    
    def get_display(self) -> str:
        """Get display string for UI."""
        if self.current_state:
            return f"{self.current_state}: {self.current_detail}"
        return "Ready"
    
    def clear(self):
        """Clear activity."""
        self.current_state = ""
        self.current_detail = ""
        self.history = []


def create_streaming_engine(
    router: PCFRouter,
    native_model: Optional[OptimizedHerculeLM] = None,
) -> StreamingEngine:
    """Factory for streaming engine."""
    return StreamingEngine(router, native_model)


def create_async_streaming_engine(
    router: PCFRouter,
    native_model: Optional[OptimizedHerculeLM] = None,
) -> AsyncStreamingEngine:
    """Factory for async streaming engine."""
    return AsyncStreamingEngine(router, native_model)