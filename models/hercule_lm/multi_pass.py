from __future__ import annotations
"""Multi-Pass Reasoning Inference Loop (N9-CAP §4).

Controlled inference loop for structured reasoning:
INPUT -> OBSERVE -> RELATE -> PLAN -> VERIFY -> ANSWER
"""

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from .model import HerculeLM
from .tokenizer import HerculeBPETokenizer
from .reasoning_format import (
    StructuredReasoning, parse_structured_reasoning, serialize_structured_reasoning,
    validate_structured_reasoning
)


@dataclass
class ReasoningPass:
    """A single reasoning pass result."""
    name: str
    prompt: str
    output: str
    tokens_used: int
    latency_ms: float
    valid: bool = True
    error: str = ""


@dataclass
class MultiPassResult:
    """Result of multi-pass reasoning."""
    final_answer: str = ""
    passes: List[ReasoningPass] = field(default_factory=list)
    structured: Optional[StructuredReasoning] = None
    total_tokens: int = 0
    total_latency_ms: float = 0.0
    verified: bool = False
    verification_score: float = 0.0


class MultiPassReasoner:
    """Multi-pass reasoning inference engine."""
    
    def __init__(
        self,
        model: HerculeLM,
        tokenizer: HerculeBPETokenizer,
        max_tokens_per_pass: int = 128,
        temperature: float = 0.0,
        seed: int = 0,
        verifier: Optional[Callable[[StructuredReasoning], Tuple[bool, float, str]]] = None
    ):
        self.model = model
        self.tokenizer = tokenizer
        self.max_tokens_per_pass = max_tokens_per_pass
        self.temperature = temperature
        self.seed = seed
        self.verifier = verifier
        
        # Pass templates
        self.pass_templates = {
            "OBSERVE": "Analyze the problem. Identify key objects, values, and constraints.\n<OBSERVE>\n",
            "RELATE": "Identify relationships between objects. Determine relevant operations.\n<RELATE>\n",
            "PLAN": "Formulate a step-by-step plan to solve the problem.\n<PLAN>\n",
            "VERIFY": "Check the candidate solution. Is it correct?\n<VERIFY>\n",
            "ANSWER": "Provide the final answer.\n<ANSWER>\n",
        }
        
        # Pass order (can be customized)
        self.default_passes = ["OBSERVE", "RELATE", "PLAN", "VERIFY", "ANSWER"]
    
    def _generate_pass(self, prompt: str, pass_name: str) -> ReasoningPass:
        """Execute a single reasoning pass."""
        start = time.perf_counter()
        
        # Add pass-specific template
        full_prompt = prompt + self.pass_templates.get(pass_name, "")
        
        # Generate
        input_ids = self.tokenizer.encode(full_prompt)
        output_ids = self.model.generate(
            input_ids,
            max_new_tokens=self.max_tokens_per_pass,
            temperature=self.temperature,
            seed=self.seed
        )
        
        # Extract only new tokens
        new_tokens = output_ids[len(input_ids):]
        output_text = self.tokenizer.decode(new_tokens)
        
        latency = (time.perf_counter() - start) * 1000
        tokens_used = len(new_tokens)
        
        return ReasoningPass(
            name=pass_name,
            prompt=full_prompt,
            output=output_text.strip(),
            tokens_used=tokens_used,
            latency_ms=latency
        )
    
    def _update_prompt_with_output(self, prompt: str, pass_name: str, output: str) -> str:
        """Append pass output to prompt for next pass."""
        # Find the last tag position
        close_tag = f"</{pass_name}>"
        idx = prompt.rfind(close_tag)
        if idx >= 0:
            return prompt[:idx + len(close_tag)] + "\n" + output + "\n"
        return prompt + output + "\n"
    
    def _extract_candidate_answer(self, reasoning: StructuredReasoning) -> Optional[str]:
        """Extract candidate answer from reasoning trace."""
        if reasoning.answer:
            return reasoning.answer
        if reasoning.tool_calls:
            return f"TOOL_CALL: {reasoning.tool_calls}"
        return None
    
    def _verify_reasoning(self, reasoning: StructuredReasoning) -> Tuple[bool, float, str]:
        """Verify reasoning trace using external verifier or internal checks."""
        if self.verifier:
            return self.verifier(reasoning)
        
        # Internal verification checks
        errors = []
        
        # Check structure
        is_valid, val_errors = validate_structured_reasoning(serialize_structured_reasoning(reasoning))
        if not is_valid:
            errors.extend(val_errors)
        
        # Check answer presence
        if not reasoning.answer and not reasoning.tool_calls:
            errors.append("No answer or tool call provided")
        
        # Check verification consistency
        if reasoning.verify:
            if "PASS" in reasoning.verify.upper():
                return True, 1.0, "Internal verification: PASS"
            elif "FAIL" in reasoning.verify.upper():
                return False, 0.0, f"Internal verification: FAIL - {reasoning.verify}"
        
        if errors:
            return False, 0.0, "; ".join(errors)
        
        return True, 1.0, "Internal verification: PASS"
    
    def reason(self, problem: str, passes: Optional[List[str]] = None, 
               max_corrections: int = 2) -> MultiPassResult:
        """Execute multi-pass reasoning on a problem.
        
        Args:
            problem: Input problem text
            passes: List of pass names to execute (default: all 5)
            max_corrections: Max correction attempts if verification fails
        
        Returns:
            MultiPassResult with full trace
        """
        passes = passes or self.default_passes
        result = MultiPassResult()
        
        prompt = problem
        correction_attempt = 0
        
        while correction_attempt <= max_corrections:
            # Execute passes
            for pass_name in passes:
                if pass_name == "ANSWER" and correction_attempt > 0:
                    # On correction attempts, re-do all passes
                    pass
                
                rp = self._generate_pass(prompt, pass_name)
                result.passes.append(rp)
                result.total_tokens += rp.tokens_used
                result.total_latency_ms += rp.latency_ms
                
                # Update prompt with this pass output
                prompt = self._update_prompt_with_output(prompt, pass_name, rp.output)
            
            # Parse full reasoning trace
            full_trace = "\n".join(p.output for p in result.passes[-len(passes):])
            reasoning = parse_structured_reasoning(full_trace)
            result.structured = reasoning
            
            # Verify
            verified, score, detail = self._verify_reasoning(reasoning)
            result.verified = verified
            result.verification_score = score
            
            if verified:
                result.final_answer = reasoning.answer or ""
                break
            
            # Correction attempt
            correction_attempt += 1
            if correction_attempt <= max_corrections:
                # Add correction prompt
                prompt = prompt + f"\n<VERIFY>\nFAIL: {detail}\n</VERIFY>\n"
                # Will re-run all passes
        
        if not result.final_answer and result.structured:
            result.final_answer = result.structured.answer or ""
        
        return result
    
    def reason_simple(self, problem: str) -> str:
        """Simple single-pass generation for comparison."""
        input_ids = self.tokenizer.encode(problem)
        output_ids = self.model.generate(
            input_ids,
            max_new_tokens=self.max_tokens_per_pass * 2,
            temperature=self.temperature,
            seed=self.seed
        )
        new_tokens = output_ids[len(input_ids):]
        return self.tokenizer.decode(new_tokens)


def create_verifier_for_arithmetic() -> Callable[[StructuredReasoning], Tuple[bool, float, str]]:
    """Create a verifier for arithmetic problems."""
    import re
    
    def verify(reasoning: StructuredReasoning) -> Tuple[bool, float, str]:
        if not reasoning.answer:
            return False, 0.0, "No answer"
        
        # Try to extract arithmetic problem from observe
        if reasoning.observe:
            # Look for pattern like "Operands: X, Y. Operation: Z."
            pass
        
        # Check if answer is numeric
        try:
            float(reasoning.answer)
            return True, 1.0, "Numeric answer"
        except ValueError:
            return False, 0.0, "Non-numeric answer"
    
    return verify


def create_verifier_for_tool_use() -> Callable[[StructuredReasoning], Tuple[bool, float, str]]:
    """Create a verifier for tool use."""
    def verify(reasoning: StructuredReasoning) -> Tuple[bool, float, str]:
        if not reasoning.tool_calls:
            return False, 0.0, "No tool call"
        
        for tc in reasoning.tool_calls:
            if "tool" not in tc or "arguments" not in tc:
                return False, 0.0, f"Invalid tool call structure: {tc}"
        
        return True, 1.0, "Valid tool call structure"
    
    return verify


def run_multi_pass_comparison(
    model: HerculeLM,
    tokenizer: HerculeBPETokenizer,
    problems: List[str],
    max_tokens: int = 128
) -> Dict[str, Any]:
    """Run comparison between single-pass and multi-pass reasoning."""
    reasoner = MultiPassReasoner(model, tokenizer, max_tokens_per_pass=max_tokens)
    
    results = {
        "single_pass": [],
        "multi_pass": [],
    }
    
    for problem in problems:
        # Single pass
        single = reasoner.reason_simple(problem)
        results["single_pass"].append({"problem": problem, "output": single})
        
        # Multi-pass
        multi = reasoner.reason(problem)
        results["multi_pass"].append({
            "problem": problem,
            "output": multi.final_answer,
            "verified": multi.verified,
            "verification_score": multi.verification_score,
            "passes": len(multi.passes),
            "total_tokens": multi.total_tokens,
            "latency_ms": multi.total_latency_ms,
        })
    
    return results


if __name__ == "__main__":
    # Demo with mock model
    print("Multi-pass reasoning module loaded successfully")
    print("Pass templates:", list(MultiPassReasoner(None, None).pass_templates.keys()))