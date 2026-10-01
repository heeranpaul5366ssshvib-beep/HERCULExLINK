#!/usr/bin/env python
"""CHECKPOINT 6: STRUCTURED OUTPUT VALIDATION"""

from models.hercule_lm.verifiers import verify_json, verify_tool_call

print("=== JSON Schema ===")
print("Valid:", verify_json('{"name": "test", "value": 42}', {"name": "str", "value": "int"}))
print("Invalid:", verify_json("not json", {"name": "str"}))
print("Missing key:", verify_json('{"value": 42}', {"name": "str", "value": "int"}))
print("Wrong type:", verify_json('{"name": 123, "value": 42}', {"name": "str", "value": "int"}))

print()
print("Tool Call:")
print("Valid:", verify_tool_call('{"tool": "calc", "arguments": {"a": 1, "b": 2}}'))
print("Missing:", verify_tool_call('{"arguments": {}}'))
print("Invalid tool:", verify_tool_call('{"tool": "unknown", "arguments": {}}', allowed=["calc"]))
print("Invalid args:", verify_tool_call('{"tool": "calc", "arguments": "not dict"}'))

# Test model's actual output
import json
import os
from models.hercule_lm.tokenizer import HerculeBPETokenizer
from models.hercule_lm.config import HerculeLMConfig
from models.hercule_lm.model import HerculeLM
from models.hercule_lm import checkpoint as ckpt

checkpoint_path = r'C:\Users\hp\HERCULE\training\checkpoints\n10\run-1790519157\step_00005557'
with open(os.path.join(checkpoint_path, 'manifest.json'), 'r') as f:
    manifest = json.load(f)

config = HerculeLMConfig.from_dict(manifest['architecture'])
tokenizer = HerculeBPETokenizer.load('training/tokenizer/hercule-bpe-nano-v1')
model = HerculeLM(config, seed=0)
ckpt.load_checkpoint(r'C:\Users\hp\HERCULE\training\checkpoints\n10\run-1790519157\step_00005557', model, strict=True)

prompts = [
    'Output JSON: {"name": "test", "value": 42}',
    'Output: {"tool": "calc", "arguments": {"a": 1, "b": 2}}',
    'Return valid JSON with keys name and value.',
    '{"name": "test"',
]

valid_count = 0
total = 0
for prompt in prompts:
    total += 1
    tokens = tokenizer.encode(prompt)
    result = model.generate(tokens, max_new_tokens=30, temperature=0.0, seed=42)
    gen_text = tokenizer.decode(result[len(tokens):]).strip()
    
    is_valid = False
    try:
        parsed = json.loads(gen_text)
        if isinstance(parsed, dict) and 'name' in parsed and 'value' in parsed:
            is_valid = True
    except:
        pass
    
    if is_valid:
        valid_count += 1
        print("VALID:", prompt[:30] + "...", "->", gen_text[:50])
    else:
        print("INVALID:", prompt[:30] + "...", "->", gen_text[:50])

print()
print("Structured Output: " + str(valid_count) + "/" + str(total) + " valid")