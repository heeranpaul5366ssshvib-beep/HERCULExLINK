#!/usr/bin/env python
"""CHECKPOINT 2: EVALUATOR SANITY CHECK"""

from models.hercule_lm.verifiers import (
    verify_math, verify_json, verify_tool_call, verify_python_tests,
    verify_refusal, verify_citation, verify_verification
)

print("=== CHECKPOINT 2: EVALUATOR SANITY CHECK ===")

# Test verify_math
print("=== verify_math ===")
print("  2+2=4:", verify_math("4", "4"))
print("  2+2=5:", verify_math("5", "4"))
print("  No number:", verify_math("hello", "4"))

# Test verify_json
print("\n=== verify_json ===")
print("  Valid JSON:", verify_json('{"key": "value"}'))
print("  Invalid JSON:", verify_json("not json"))
print("  Missing key:", verify_json('{"a": 1}', {"b": "int"}))
print("  Type mismatch:", verify_json('{"a": "not int"}', {"a": "int"}))

# Test verify_tool_call
print("\n=== verify_tool_call ===")
print("  Valid:", verify_tool_call('{"tool": "calc", "arguments": {}}'))
print("  Missing tool:", verify_tool_call('{"arguments": {}}'))
print("  Invalid tool:", verify_tool_call('{"tool": "nonexistent", "arguments": {}}', allowed=["calc"]))

# Test verify_python_tests
print("\n=== verify_python_tests ===")
code = "def add(a, b): return a + b"
tests = [{"call": "add(2, 3)", "expect": 5}, {"call": "add(0, 0)", "expect": 0}]
print("  Passing tests:", verify_python_tests(code, tests))
code_bad = "def add(a, b): return a - b"
print("  Failing tests:", verify_python_tests(code_bad, tests))

# Test verify_refusal
print("\n=== verify_refusal ===")
print("  Refusal:", verify_refusal("I cannot comply with that request"))
print("  No refusal:", verify_refusal("Sure I can help"))

# Test verify_citation
print("\n=== verify_citation ===")
print("  Citation present:", verify_citation("Source: Wikipedia", "Wikipedia"))
print("  Missing:", verify_citation("No citation here", "Wikipedia"))

# Test verify_verification
print("\n=== verify_verification ===")
print("  Correct:", verify_verification("The answer is CORRECT", "CORRECT|"))
print("  Incorrect with correction:", verify_verification("INCORRECT. The answer is 4", "INCORRECT|4"))
print("  Incorrect no correction:", verify_verification("INCORRECT", "INCORRECT|4"))

print("\n=== EVALUATOR SANITY CHECK: PASS ===")