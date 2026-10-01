import sys
sys.path.insert(0, r'c:\Users\hp\HERCULE')

# Try a very simple import test first
print("Testing imports...")
try:
    from cognition.capabilities.proposal import CapabilityProposal, parse_proposal_payload
    print("  proposal.py: OK")
except Exception as e:
    print(f"  proposal.py: FAILED {e}")

try:
    from cognition.capabilities.semantic import SemanticCapabilityProposer, render_capability_prompt
    print("  semantic.py: OK")
except Exception as e:
    print(f"  semantic.py: FAILED {e}")

try:
    from cognition.capabilities.hybrid import resolve_capabilities, HybridMode
    print("  hybrid.py: OK")
except Exception as e:
    print(f"  hybrid.py: FAILED {e}")

try:
    from cognition.capabilities.registry import CapabilityRegistry
    print("  registry.py: OK")
except Exception as e:
    print(f"  registry.py: FAILED {e}")

try:
    from cognition.capabilities.vocabulary import normalize_name
    print("  vocabulary.py: OK")
except Exception as e:
    print(f"  vocabulary.py: FAILED {e}")

try:
    from cognition.capabilities.inference import infer_capabilities
    print("  inference.py: OK")
except Exception as e:
    print(f"  inference.py: FAILED {e}")

try:
    from cognition.capabilities.effects import default_effect_for
    print("  effects.py: OK")
except Exception as e:
    print(f"  effects.py: FAILED {e}")

try:
    from cognition.planner.planner import Planner
    print("  planner.py: OK")
except Exception as e:
    print(f"  planner.py: FAILED {e}")

try:
    from cognition.planner.capable import build_capable_plan
    print("  capable.py: OK")
except Exception as e:
    print(f"  capable.py: FAILED {e}")

try:
    from cognition.planner.validation import validate_plan
    print("  validation.py: OK")
except Exception as e:
    print(f"  validation.py: FAILED {e}")

try:
    from system.config.semantic_config import load_semantic_config
    print("  semantic_config.py: OK")
except Exception as e:
    print(f"  semantic_config.py: FAILED {e}")

try:
    from system.observability.trace import Tracer, trace_semantic
    print("  trace.py: OK")
except Exception as e:
    print(f"  trace.py: FAILED {e}")

try:
    from evaluation.semantic_eval import load_capability_dataset, run_capability_benchmark, score_sets
    print("  semantic_eval.py: OK")
except Exception as e:
    print(f"  semantic_eval.py: FAILED {e}")

try:
    from brain.brain import Brain
    print("  brain.py: OK")
except Exception as e:
    print(f"  brain.py: FAILED {e}")

print("\nRunning a quick smoke test...")
try:
    from cognition.capabilities.proposal import parse_proposal_payload
    from tests.support_semantic import entry, payload
    proposals, warnings, errors = parse_proposal_payload(payload(
        entry("FILE_READ", 0.97, "inspect file"), entry("CODE_EDIT", 0.91, "modify", required=False)))
    assert [p.name for p in proposals] == ["FILE_READ", "CODE_EDIT"]
    print("  Smoke test: PASSED")
except Exception as e:
    print(f"  Smoke test: FAILED {e}")
    import traceback
    traceback.print_exc()

print("\nDone.")
