from __future__ import annotations
"""Structured Reasoning Format (N9-CAP §1).

Machine-verifiable intermediate representations for reasoning.
Uses compact tags: OBSERVE, RELATE, PLAN, VERIFY, ANSWER.
"""

import re
import json
import numpy as np
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum


class ReasoningTag(Enum):
    OBSERVE = "OBSERVE"
    RELATE = "RELATE"
    PLAN = "PLAN"
    VERIFY = "VERIFY"
    ANSWER = "ANSWER"
    TOOL_CALL = "TOOL_CALL"
    TOOL_RESULT = "TOOL_RESULT"


# Tag regex patterns (must match tokenizer specials)
TAG_PATTERNS = {
    ReasoningTag.OBSERVE: (r"<OBSERVE>", r"</OBSERVE>"),
    ReasoningTag.RELATE: (r"<RELATE>", r"</RELATE>"),
    ReasoningTag.PLAN: (r"<PLAN>", r"</PLAN>"),
    ReasoningTag.VERIFY: (r"<VERIFY>", r"</VERIFY>"),
    ReasoningTag.ANSWER: (r"<ANSWER>", r"</ANSWER>"),
    ReasoningTag.TOOL_CALL: (r"<TOOL_CALL>", r"</TOOL_CALL>"),
    ReasoningTag.TOOL_RESULT: (r"<TOOL_RESULT>", r"</TOOL_RESULT>"),
}


@dataclass
class StructuredReasoning:
    """Parsed structured reasoning trace."""
    observe: Optional[str] = None
    relate: Optional[str] = None
    plan: Optional[str] = None
    verify: Optional[str] = None
    answer: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    raw: str = ""
    
    def is_valid(self) -> bool:
        """Check if trace has minimum required structure."""
        return self.answer is not None or self.tool_calls != []
    
    def has_verification(self) -> bool:
        return self.verify is not None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "observe": self.observe,
            "relate": self.relate,
            "plan": self.plan,
            "verify": self.verify,
            "answer": self.answer,
            "tool_calls": self.tool_calls,
            "tool_results": self.tool_results,
        }


def parse_structured_reasoning(text: str) -> StructuredReasoning:
    """Parse structured reasoning from text with tags.
    
    Deterministic parsing - first match for each tag.
    """
    result = StructuredReasoning(raw=text)
    
    for tag, (open_pat, close_pat) in TAG_PATTERNS.items():
        pattern = open_pat + r"(.*?)" + close_pat
        matches = re.findall(pattern, text, re.DOTALL)
        if matches:
            content = matches[0].strip()
            if tag == ReasoningTag.OBSERVE:
                result.observe = content
            elif tag == ReasoningTag.RELATE:
                result.relate = content
            elif tag == ReasoningTag.PLAN:
                result.plan = content
            elif tag == ReasoningTag.VERIFY:
                result.verify = content
            elif tag == ReasoningTag.ANSWER:
                result.answer = content
            elif tag == ReasoningTag.TOOL_CALL:
                # Try to parse as JSON
                try:
                    result.tool_calls.append(json.loads(content))
                except json.JSONDecodeError:
                    result.tool_calls.append({"raw": content})
            elif tag == ReasoningTag.TOOL_RESULT:
                # Try to parse as JSON
                try:
                    result.tool_results.append(json.loads(content))
                except json.JSONDecodeError:
                    result.tool_results.append({"content": content})
    
    return result


def serialize_structured_reasoning(sr: StructuredReasoning) -> str:
    """Serialize structured reasoning to tagged format."""
    parts = []
    if sr.observe is not None:
        parts.append(f"<OBSERVE>\n{sr.observe}\n</OBSERVE>")
    if sr.relate is not None:
        parts.append(f"<RELATE>\n{sr.relate}\n</RELATE>")
    if sr.plan is not None:
        parts.append(f"<PLAN>\n{sr.plan}\n</PLAN>")
    if sr.verify is not None:
        parts.append(f"<VERIFY>\n{sr.verify}\n</VERIFY>")
    if sr.answer is not None:
        parts.append(f"<ANSWER>\n{sr.answer}\n</ANSWER>")
    for tc in sr.tool_calls:
        parts.append(f"<TOOL_CALL>\n{json.dumps(tc)}\n</TOOL_CALL>")
    for tr in sr.tool_results:
        parts.append(f"<TOOL_RESULT>\n{json.dumps(tr)}\n</TOOL_RESULT>")
    return "\n".join(parts)


def validate_structured_reasoning(text: str) -> Tuple[bool, List[str]]:
    """Validate structured reasoning format.
    
    Returns (is_valid, list_of_errors).
    """
    errors = []
    sr = parse_structured_reasoning(text)
    
    # Check for unclosed tags
    for tag, (open_pat, close_pat) in TAG_PATTERNS.items():
        open_count = len(re.findall(open_pat, text))
        close_count = len(re.findall(close_pat, text))
        if open_count != close_count:
            errors.append(f"Unclosed tag {tag.value}: {open_count} open, {close_count} close")
    
    # Check minimum structure
    if not sr.is_valid():
        errors.append("Missing ANSWER or TOOL_CALL")
    
    # Check JSON in tool calls
    for i, tc in enumerate(sr.tool_calls):
        if "raw" in tc:
            errors.append(f"Tool call {i} has invalid JSON: {tc['raw'][:50]}")
    
    return len(errors) == 0, errors


# --------------------------------------------------
# Domain-specific structured generators

def make_arithmetic_reasoning(a: int, b: int, op: str, answer: int, 
                               show_work: bool = True) -> StructuredReasoning:
    """Create structured reasoning for arithmetic."""
    op_names = {'+': 'addition', '-': 'subtraction', '*': 'multiplication', '/': 'division'}
    op_name = op_names.get(op, op)
    
    sr = StructuredReasoning()
    if show_work:
        sr.observe = f"Operands: {a}, {b}. Operation: {op_name}."
        sr.relate = f"Compute {a} {op} {b}."
        sr.plan = f"Apply {op_name} to {a} and {b}."
    sr.answer = str(answer)
    sr.verify = f"PASS: {a} {op} {b} = {answer}"
    return sr


def make_comparison_reasoning(a: int, b: int, op: str, answer: bool) -> StructuredReasoning:
    """Create structured reasoning for comparison."""
    op_names = {'>': 'greater than', '<': 'less than', '==': 'equal to', 
                '!=': 'not equal to', '>=': 'greater than or equal to', '<=': 'less than or equal to'}
    op_name = op_names.get(op, op)
    
    sr = StructuredReasoning()
    sr.observe = f"Compare {a} and {b} using {op_name}."
    sr.relate = f"{a} {op} {b} evaluates to {str(answer).lower()}."
    sr.plan = f"Return {'Yes' if answer else 'No'}."
    sr.answer = "Yes." if answer else "No."
    sr.verify = f"PASS: {a} {op} {b} is {str(answer).lower()}"
    return sr


def make_tool_call_reasoning(tool: str, args: Dict[str, Any], 
                              result: Any, verified: bool = True) -> StructuredReasoning:
    """Create structured reasoning with tool call."""
    sr = StructuredReasoning()
    sr.observe = f"Need to use {tool} tool with arguments: {json.dumps(args)}"
    sr.plan = f"Call {tool} tool."
    sr.tool_calls = [{"tool": tool, "arguments": args}]
    sr.tool_results = [{"result": result}]
    sr.verify = "PASS" if verified else "FAIL"
    sr.answer = str(result)
    return sr


def make_correction_reasoning(problem: str, wrong_answer: Any, 
                               correct_answer: Any, error_type: str) -> StructuredReasoning:
    """Create structured reasoning showing correction."""
    sr = StructuredReasoning()
    sr.observe = f"Problem: {problem}. Initial answer: {wrong_answer}. Error: {error_type}."
    sr.relate = f"The correct answer is {correct_answer}."
    sr.plan = f"Correct the error and provide verified answer."
    sr.verify = f"FAIL -> CORRECT: {wrong_answer} was wrong, {correct_answer} is correct."
    sr.answer = str(correct_answer)
    return sr


def make_arc_reasoning(input_grid: List[List[int]], output_grid: List[List[int]],
                        transform: str) -> StructuredReasoning:
    """Create structured reasoning for ARC grid task."""
    sr = StructuredReasoning()
    
    # Convert to native Python types
    def to_native(obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, list):
            return [to_native(v) for v in obj]
        return obj
    
    input_grid = to_native(input_grid)
    output_grid = to_native(output_grid)
    
    sr.observe = f"Input grid: {input_grid}. Detected pattern: {transform}."
    sr.relate = f"Objects: identify grid structure. Relations: {transform} operation applies."
    sr.plan = f"Apply {transform} to each cell."
    sr.answer = json.dumps(output_grid)
    sr.verify = f"PASS: {transform} produces expected output grid."
    return sr


# --------------------------------------------------
# Round-trip test

def test_round_trip():
    """Test parse -> serialize -> parse round-trip."""
    # Test basic arithmetic
    sr1 = make_arithmetic_reasoning(25, 4, '*', 100)
    text1 = serialize_structured_reasoning(sr1)
    sr1_parsed = parse_structured_reasoning(text1)
    assert sr1.answer == sr1_parsed.answer
    assert sr1.verify == sr1_parsed.verify
    
    # Test tool call
    sr2 = make_tool_call_reasoning("calculator", {"expression": "25 * 4"}, 100)
    text2 = serialize_structured_reasoning(sr2)
    sr2_parsed = parse_structured_reasoning(text2)
    assert sr2.tool_calls == sr2_parsed.tool_calls
    assert sr2.tool_results == sr2_parsed.tool_results
    
    # Test correction
    sr3 = make_correction_reasoning("25 * 4", 90, 100, "arithmetic_error")
    text3 = serialize_structured_reasoning(sr3)
    sr3_parsed = parse_structured_reasoning(text3)
    assert sr3.answer == sr3_parsed.answer
    assert "FAIL" in sr3_parsed.verify
    
    # Test validation
    valid_text = "<OBSERVE>test</OBSERVE><ANSWER>42</ANSWER>"
    is_valid, errors = validate_structured_reasoning(valid_text)
    assert is_valid, f"Valid text failed: {errors}"
    
    invalid_text = "<OBSERVE>test<ANSWER>42</ANSWER>"  # unclosed OBSERVE
    is_valid, errors = validate_structured_reasoning(invalid_text)
    assert not is_valid
    assert any("Unclosed" in e for e in errors)
    
    print("All round-trip tests passed!")


if __name__ == "__main__":
    test_round_trip()
    
    # Demo
    sr = make_arithmetic_reasoning(25, 4, '*', 100)
    print("Structured reasoning:")
    print(serialize_structured_reasoning(sr))
    print()
    print("Parsed back:")
    parsed = parse_structured_reasoning(serialize_structured_reasoning(sr))
    print(f"  observe: {parsed.observe}")
    print(f"  verify: {parsed.verify}")
    print(f"  answer: {parsed.answer}")