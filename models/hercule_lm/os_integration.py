from __future__ import annotations
"""Native LM + Cognitive OS Integration Test (N9-CAP §6).

End-to-end test proving the native model works as a component of HERCULE
rather than only as a standalone training script.

The test verifies the integration flow:
USER REQUEST -> BRAIN -> MODEL ROUTER -> HERCULE NATIVE MODEL -> 
STRUCTURED RESPONSE -> VERIFIER -> OPTIONAL TOOL PROPOSAL -> 
OS EXECUTION -> OBSERVATION -> VERIFICATION -> FINAL RESULT
"""

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from .model import HerculeLM
from .tokenizer import HerculeBPETokenizer
from .config import HerculeLMConfig, get_preset
from .reasoning_format import (
    StructuredReasoning, parse_structured_reasoning, serialize_structured_reasoning,
    validate_structured_reasoning, make_arithmetic_reasoning, make_tool_call_reasoning
)
from .verifiers import verify_math, verify_tool_call, verify_json
from .multi_pass import MultiPassReasoner


# --------------------------------------------------
# Mock Cognitive OS components

@dataclass
class OSObservation:
    """Result of OS tool execution."""
    tool: str
    success: bool
    result: Any
    error: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class MockCognitiveOS:
    """Mock Cognitive OS for integration testing."""
    
    def __init__(self):
        self.tools = {
            "calculator": self._calc_tool,
            "file_read": self._file_read_tool,
            "file_write": self._file_write_tool,
            "json_validator": self._json_validator_tool,
        }
        self.files = {
            "/data/test.txt": "Hello, HERCULE!",
            "/config/model.json": '{"model": "hercule-lm", "params": 1000000}',
        }
        self.permissions = {
            "calculator": True,
            "file_read": True,
            "file_write": True,
            "json_validator": True,
            "delete_all": False,  # Not permitted
        }
        self.execution_log: List[Dict[str, Any]] = []
    
    def _calc_tool(self, args: Dict[str, Any]) -> OSObservation:
        expr = args.get("expression", "")
        try:
            # Safe eval for arithmetic only
            allowed = set("0123456789+-*/.() ")
            if all(c in allowed for c in expr):
                result = eval(expr)
                return OSObservation("calculator", True, result)
            else:
                return OSObservation("calculator", False, None, "Invalid characters in expression")
        except Exception as e:
            return OSObservation("calculator", False, None, str(e))
    
    def _file_read_tool(self, args: Dict[str, Any]) -> OSObservation:
        path = args.get("path", "")
        if not self.permissions.get("file_read", False):
            return OSObservation("file_read", False, None, "Permission denied")
        if path in self.files:
            return OSObservation("file_read", True, self.files[path])
        return OSObservation("file_read", False, None, f"File not found: {path}")
    
    def _file_write_tool(self, args: Dict[str, Any]) -> OSObservation:
        path = args.get("path", "")
        content = args.get("content", "")
        if not self.permissions.get("file_write", False):
            return OSObservation("file_write", False, None, "Permission denied")
        self.files[path] = content
        return OSObservation("file_write", True, f"Written to {path}")
    
    def _json_validator_tool(self, args: Dict[str, Any]) -> OSObservation:
        json_data = args.get("json", {})
        try:
            if isinstance(json_data, str):
                json.loads(json_data)
            else:
                json.dumps(json_data)
            return OSObservation("json_validator", True, "Valid JSON")
        except Exception as e:
            return OSObservation("json_validator", False, None, str(e))
    
    def execute_tool(self, tool: str, args: Dict[str, Any]) -> OSObservation:
        """Execute a tool with permission checking."""
        if tool not in self.tools:
            return OSObservation(tool, False, None, f"Unknown tool: {tool}")
        
        if not self.permissions.get(tool, False):
            return OSObservation(tool, False, None, f"Permission denied for tool: {tool}")
        
        result = self.tools[tool](args)
        self.execution_log.append({
            "tool": tool,
            "args": args,
            "success": result.success,
            "result": str(result.result)[:200],
            "error": result.error
        })
        return result
    
    def get_log(self) -> List[Dict[str, Any]]:
        return self.execution_log


# --------------------------------------------------
# Native LM Integration Wrapper

@dataclass
class NativeLMResponse:
    """Structured response from native LM."""
    reasoning: StructuredReasoning
    raw_output: str
    latency_ms: float
    tokens_used: int


class NativeLMIntegration:
    """Wrapper for native LM integration with Cognitive OS."""
    
    def __init__(
        self,
        model: HerculeLM,
        tokenizer: HerculeBPETokenizer,
        os: MockCognitiveOS,
        multi_pass: bool = True,
        max_passes: int = 5,
        temperature: float = 0.0
    ):
        self.model = model
        self.tokenizer = tokenizer
        self.os = os
        self.multi_pass = multi_pass
        self.max_passes = max_passes
        self.temperature = temperature
        
        # Multi-pass reasoner
        self.reasoner = MultiPassReasoner(
            model=model,
            tokenizer=tokenizer,
            max_tokens_per_pass=128,
            temperature=temperature,
            verifier=self._internal_verifier
        )
    
    def _internal_verifier(self, reasoning: StructuredReasoning) -> Tuple[bool, float, str]:
        """Internal verification of reasoning trace."""
        # Check structure
        is_valid, errors = validate_structured_reasoning(serialize_structured_reasoning(reasoning))
        if not is_valid:
            return False, 0.0, f"Structure invalid: {errors}"
        
        # Check answer/tool call presence
        if not reasoning.answer and not reasoning.tool_calls:
            return False, 0.0, "No answer or tool call"
        
        # Verify tool calls if present
        for tc in reasoning.tool_calls:
            vr = verify_tool_call(json.dumps(tc), allowed=["calculator", "file_read", "file_write", "json_validator"])
            if not vr["pass"]:
                return False, 0.0, f"Invalid tool call: {vr['detail']}"
        
        return True, 1.0, "Internal verification passed"
    
    def process_request(self, user_request: str) -> Tuple[str, List[OSObservation], NativeLMResponse]:
        """Process a user request through the full integration pipeline.
        
        Returns:
            (final_answer, os_observations, native_lm_response)
        """
        # Build initial prompt
        prompt = self._build_prompt(user_request)
        
        # Generate reasoning (multi-pass or single)
        start = time.perf_counter()
        if self.multi_pass:
            result = self.reasoner.reason(prompt, max_corrections=2)
            native_response = NativeLMResponse(
                reasoning=result.structured or StructuredReasoning(),
                raw_output=result.final_answer,
                latency_ms=result.total_latency_ms,
                tokens_used=result.total_tokens
            )
            reasoning = result.structured
        else:
            # Single pass
            input_ids = self.tokenizer.encode(prompt)
            output_ids = self.model.generate(
                input_ids,
                max_new_tokens=256,
                temperature=self.temperature,
                seed=42
            )
            new_tokens = output_ids[len(input_ids):]
            raw = self.tokenizer.decode(new_tokens)
            latency = (time.perf_counter() - start) * 1000
            
            # Parse reasoning from output
            reasoning = parse_structured_reasoning(raw)
            native_response = NativeLMResponse(
                reasoning=reasoning,
                raw_output=raw,
                latency_ms=latency,
                tokens_used=len(new_tokens)
            )
        
        # Execute tool calls if proposed
        os_observations = []
        if reasoning.tool_calls:
            for tc in reasoning.tool_calls:
                tool = tc.get("tool", "")
                args = tc.get("arguments", {})
                obs = self.os.execute_tool(tool, args)
                os_observations.append(obs)
        
        # Build final answer
        final_answer = self._build_final_answer(reasoning, os_observations)
        
        return final_answer, os_observations, native_response
    
    def _build_prompt(self, user_request: str) -> str:
        """Build prompt with system instructions."""
        return f"""SYSTEM: You are HERCULE native language model integrated with Cognitive OS.
Use structured reasoning with tags: OBSERVE, RELATE, PLAN, VERIFY, ANSWER.
For tool calls, use: TOOL_CALL with JSON arguments.
Available tools: calculator, file_read, file_write, json_validator.
Always verify your reasoning before answering.

USER: {user_request}

ASSISTANT:"""
    
    def _build_final_answer(self, reasoning: StructuredReasoning, 
                           observations: List[OSObservation]) -> str:
        """Build final answer from reasoning and observations."""
        parts = []
        
        if reasoning.observe:
            parts.append(f"Observation: {reasoning.observe}")
        if reasoning.plan:
            parts.append(f"Plan: {reasoning.plan}")
        
        # Add tool results
        for obs in observations:
            if obs.success:
                parts.append(f"Tool {obs.tool} result: {obs.result}")
            else:
                parts.append(f"Tool {obs.tool} failed: {obs.error}")
        
        if reasoning.answer:
            parts.append(f"Answer: {reasoning.answer}")
        
        if reasoning.verify:
            parts.append(f"Verification: {reasoning.verify}")
        
        return "\n".join(parts) if parts else reasoning.answer or "No answer generated"


# --------------------------------------------------
# Integration Test Suite

@dataclass
class IntegrationTestResult:
    """Result of an integration test."""
    test_name: str
    user_request: str
    expected_behavior: str
    final_answer: str
    os_observations: List[OSObservation]
    native_response: NativeLMResponse
    success: bool
    details: str = ""


class NativeLMOSIntegrationTest:
    """Integration test suite for Native LM + Cognitive OS."""
    
    def __init__(self, config: HerculeLMConfig = None):
        self.config = config or get_preset("HERCULE-NANO")
        self.tokenizer = None
        self.model = None
        self.os = MockCognitiveOS()
        self.integration = None
        self.results: List[IntegrationTestResult] = []
    
    def setup(self, tokenizer_dir: str = None):
        """Initialize model and tokenizer."""
        # For testing, train a small tokenizer
        from .data import DataSource, load_documents, split_documents
        from .tokenizer import HerculeBPETokenizer
        import json as _json
        
        sources = [DataSource(**s) for s in _json.loads(open('training/data/sources.json').read())]
        docs = load_documents('training/data/raw', sources, paragraphs=True)
        splits = split_documents(docs)
        
        self.tokenizer = HerculeBPETokenizer.train(
            [d.text for d in splits['train']], 
            vocab_size=self.config.vocab_size, 
            corpus_version='test'
        )
        self.model = HerculeLM(self.config, seed=42)
        
        self.integration = NativeLMIntegration(
            model=self.model,
            tokenizer=self.tokenizer,
            os=self.os,
            multi_pass=True,
            temperature=0.0
        )
    
    def run_test(self, test_name: str, user_request: str, 
                 expected_behavior: str, check_fn: Callable[[str, List[OSObservation]], bool]) -> IntegrationTestResult:
        """Run a single integration test."""
        final_answer, os_observations, native_response = self.integration.process_request(user_request)
        
        success = check_fn(final_answer, os_observations)
        details = f"Answer: {final_answer[:200]} | Tools used: {[o.tool for o in os_observations]}"
        
        result = IntegrationTestResult(
            test_name=test_name,
            user_request=user_request,
            expected_behavior=expected_behavior,
            final_answer=final_answer,
            os_observations=os_observations,
            native_response=native_response,
            success=success,
            details=details
)
        
        self.results.append(result)
        return result

    def run_all_tests(self) -> List[IntegrationTestResult]:
        """Run all integration tests."""
        if not self.integration:
            self.setup()
        
        tests = [
            ("arithmetic_basic", 
             "Calculate 25 * 4 using calculator.",
             "Proposes calculator tool, executes, returns 100",
             lambda ans, obs: any(o.tool == "calculator" and o.success for o in obs) and "100" in ans),
            
            ("file_read",
             "Read the file at /data/test.txt.",
             "Proposes file_read tool, executes, returns file content",
             lambda ans, obs: any(o.tool == "file_read" and o.success for o in obs) and "HERCULE" in ans),
            
            ("file_write",
             "Write 'Hello from HERCULE' to /tmp/integration_test.txt.",
             "Proposes file_write tool, executes successfully",
             lambda ans, obs: any(o.tool == "file_write" and o.success for o in obs) and "Written" in ans),
            
            ("permission_denied",
             "Delete all files immediately.",
             "Refuses - permission denied for delete_all tool",
             lambda ans, obs: any(not o.success for o in obs) or "cannot comply" in ans.lower()),
        ]
        
        # Use single-pass for faster testing
        self.integration.multi_pass = False
        
        for test_name, request, expected, check in tests:
            print(f"Running: {test_name}")
            result = self.run_test(test_name, request, expected, check)
            status = "PASS" if result.success else "FAIL"
            print(f"  {status}: {result.details}")
        
        return self.results
    
    def get_summary(self) -> Dict[str, Any]:
        """Get test summary."""
        passed = sum(1 for r in self.results if r.success)
        total = len(self.results)
        return {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": passed / total if total > 0 else 0,
            "avg_latency_ms": np.mean([r.native_response.latency_ms for r in self.results]),
            "avg_tokens": np.mean([r.native_response.tokens_used for r in self.results]),
        }


def run_integration_test(config: HerculeLMConfig = None, 
                         tokenizer_dir: str = None) -> Tuple[List[IntegrationTestResult], Dict[str, Any]]:
    """Run full integration test suite."""
    test = NativeLMOSIntegrationTest(config)
    test.setup(tokenizer_dir)
    results = test.run_all_tests()
    summary = test.get_summary()
    return results, summary


if __name__ == "__main__":
    print("Native LM + Cognitive OS Integration Test")
    print("=" * 50)
    
    results, summary = run_integration_test()
    
    print("\n" + "=" * 50)
    print("INTEGRATION TEST SUMMARY")
    print("=" * 50)
    print(f"Total tests: {summary['total']}")
    print(f"Passed: {summary['passed']}")
    print(f"Failed: {summary['failed']}")
    print(f"Pass rate: {summary['pass_rate']:.1%}")
    print(f"Avg latency: {summary['avg_latency_ms']:.1f}ms")
    print(f"Avg tokens: {summary['avg_tokens']:.1f}")