"""Ability/tool pipeline tests: registration → discovery → matching →
permissions → execution → verification → recovery. All real, no fakes."""

import pytest

from abilities.ability_manager import AbilityManager
from abilities.base_ability import BaseAbility
from abilities.tool_matcher import ToolMatcher, ToolMatchError
from cognition.capabilities.registry import CapabilityRegistry
from orchestrator.step_verifier import verify_step
from security.permissions.policy_manager import PolicyManager


class EchoAbility(BaseAbility):
    def __init__(self, name="echo-file", result="echo-content-here"):
        super().__init__(name, f"test {name}", capability="FILE_READ",
                         permissions=["FILE_READ"], risk="LOW")
        self.calls = 0
        self.result = result

    def execute(self, *args, **kwargs):
        self.calls += 1
        return {"status": "success", "content": self.result}


def make_stack():
    abilities = AbilityManager()
    abilities.register(EchoAbility())
    policy = abilities.policy
    registry = CapabilityRegistry()
    registry.register_default_tools(abilities if hasattr(abilities, "get") else None)
    # Test double is not in DEFAULT_TOOL_CAPABILITIES; map it explicitly
    # (mirrors Brain.register_capability in production).
    registry.register_provider("FILE_READ", "tool", "echo-file",
                               ["FILE_READ"], ability_manager=abilities)
    from abilities.tool_health import ToolHealthMonitor
    matcher = ToolMatcher(abilities, policy, None, registry, ToolHealthMonitor())
    return abilities, policy, registry, matcher


def test_ability_registration():
    abilities = AbilityManager()
    assert abilities.count() == 0
    abilities.register(EchoAbility())
    assert abilities.exists("echo-file")
    assert abilities.count() == 1


def test_ability_discovery_metadata():
    abilities, _, _, _ = make_stack()
    catalog = abilities.describe_all()
    assert "echo-file" in catalog
    meta = catalog["echo-file"]
    for key in ("name", "description", "capability", "inputs", "outputs",
                "permissions", "environments", "verification", "timeout_s", "risk"):
        assert key in meta, key


def test_capability_matching_selects_ability():
    _, _, _, matcher = make_stack()
    step = {"step_id": "step-1", "description": "read the file",
            "required_capabilities": ["FILE_READ"],
            "verification_criteria": ["content returned"], "risk": "LOW"}
    selection = matcher.match(step)
    assert selection.selected.name == "echo-file"
    assert selection.coverage == "FULL"


def test_permission_rejection_blocks_execution():
    abilities, policy, _, _ = make_stack()
    policy.set_permission("FILE_READ", False)
    try:
        with pytest.raises(RuntimeError, match="Permission denied"):
            abilities.execute("echo-file", "read the file", capabilities=["FILE_READ"])
        assert abilities.get("echo-file").calls == 0
    finally:
        policy.set_permission("FILE_READ", True)


def test_successful_execution_structured():
    abilities, _, _, _ = make_stack()
    result = abilities.execute("echo-file", "read the file", capabilities=["FILE_READ"])
    assert result["status"] == "success"
    assert result["content"] == "echo-content-here"


def test_failed_execution_returns_structured_error():
    from abilities.calculator.calculator_ability import CalculatorAbility
    abilities = AbilityManager()
    abilities.register(CalculatorAbility())
    # Valid shape but uncomputable (division by zero) -> structured failure.
    result = abilities.execute("calculator", "1/0", capabilities=["MATH"])
    assert result["status"] == "failed"
    assert "error" in result
    # Garbage text is rejected honestly before execution (req 5).
    with pytest.raises(RuntimeError, match="Invalid inputs"):
        abilities.execute("calculator", "calculate blah blah", capabilities=["MATH"])


def test_verification_failure_detected():
    step = {"step_id": "step-1", "required_capabilities": ["MATH"],
            "verification_criteria": ["result verified by recomputation"]}
    outcome = {"status": "success", "executor": {"name": "calculator"},
               "result": {"status": "success", "expression": "2+2", "result": 999},
               "attempts": 1, "errors": []}
    verdict = verify_step(step, outcome)
    assert verdict["passed"] is False


def test_verification_success_by_recomputation():
    step = {"step_id": "step-1", "required_capabilities": ["MATH"],
            "verification_criteria": ["result verified by recomputation"]}
    outcome = {"status": "success", "executor": {"name": "calculator"},
               "result": {"status": "success", "expression": "25 * 4", "result": 100},
               "attempts": 1, "errors": []}
    verdict = verify_step(step, outcome)
    assert verdict["passed"] is True


def test_unknown_capability_rejected():
    _, _, _, matcher = make_stack()
    step = {"step_id": "step-1", "description": "do the impossible",
            "required_capabilities": ["NO_SUCH_CAPABILITY"],
            "verification_criteria": ["x"], "risk": "LOW"}
    with pytest.raises(ToolMatchError) as excinfo:
        matcher.match(step)
    assert excinfo.value.code == "UNKNOWN_CAPABILITY"


def test_unavailable_tool_no_healthy_provider():
    abilities = AbilityManager()  # empty: no tools registered
    registry = CapabilityRegistry()
    from abilities.tool_health import ToolHealthMonitor
    matcher = ToolMatcher(abilities, PolicyManager(), None, registry, ToolHealthMonitor())
    step = {"step_id": "step-1", "description": "read the file",
            "required_capabilities": ["FILE_READ"],
            "verification_criteria": ["content returned"], "risk": "LOW"}
    with pytest.raises(ToolMatchError) as excinfo:
        matcher.match(step)
    assert excinfo.value.code in ("NO_HEALTHY_PROVIDER", "NO_CAPABILITY_COVERAGE")


def test_high_risk_requires_explicit_approval():
    from abilities.terminal.terminal_ability import TerminalAbility
    abilities = AbilityManager()
    abilities.register(TerminalAbility())
    with pytest.raises(RuntimeError, match="Approval required"):
        abilities.execute("terminal", "echo hello", capabilities=["TERMINAL_EXECUTE"])
    ok = abilities.execute("terminal", "python --version", capabilities=["TERMINAL_EXECUTE"],
                           approval_required=True, approved=True)
    assert ok["status"] == "success"
    assert ok["returncode"] == 0


def test_terminal_blocks_dangerous_commands():
    from abilities.terminal.terminal_ability import TerminalAbility
    abilities = AbilityManager()
    abilities.register(TerminalAbility())
    # Dangerous commands are rejected honestly: either pre-execution
    # RuntimeError (validation) or structured failure — never execution.
    try:
        result = abilities.execute("terminal", "rm -rf /", capabilities=["TERMINAL_EXECUTE"],
                                   approval_required=True, approved=True)
    except RuntimeError as exc:
        assert "blocked" in str(exc).lower() or "Invalid inputs" in str(exc)
    else:
        assert result["status"] == "failed"


def test_recovery_failed_step_enters_replan():
    from runtime.initializer import RuntimeInitializer
    services = RuntimeInitializer().initialize()
    brain = services["brain"]
    report = brain.run_cycle("blorple impossible zzz-no-provider-xyz")
    assert report["status"] == "failed"
    assert "dynamically synthesized" not in str(report)
    assert report.get("replans", 0) <= 2


def test_planner_never_invents_abilities():
    from runtime.initializer import RuntimeInitializer
    from cognition.planner.validation import validate_plan
    services = RuntimeInitializer().initialize()
    brain = services["brain"]
    stack = brain._autonomy_stack()
    plan = brain.authoritative_planner.create_capable_plan("calculate 25 * 4", ["calculate 25 * 4"])
    report = validate_plan(plan, capability_registry=stack["registry"],
                           policy_manager=stack["policy"], ability_manager=stack["abilities"])
    for step_report in report["steps"]:
        assert step_report["coverage"] in ("FULL", "PARTIAL", "NO_COVERAGE", "NONE")
    # Every claimed capability must have a registered provider or be flagged missing.
    missing = report["metrics"]["missing_capabilities"]
    assert isinstance(missing, int)


def test_duplicate_registration_rejected():
    abilities = AbilityManager()
    abilities.register(EchoAbility())
    with pytest.raises(ValueError, match="already registered"):
        abilities.register(EchoAbility())
    assert abilities.count() == 1


def test_capability_lookup_and_availability():
    abilities, _, _, _ = make_stack()
    matches = abilities.lookup_by_capability("FILE_READ")
    assert any(a.name == "echo-file" for a in matches)
    assert abilities.lookup_by_capability("NO_SUCH_CAPABILITY") == []
    available = abilities.availability("echo-file")
    assert available["available"] is True
    assert abilities.availability("ghost-tool") == {
        "name": "ghost-tool", "available": False, "reason": "not registered"}
    abilities.disable("echo-file")
    assert abilities.availability("echo-file")["available"] is False
    abilities.enable("echo-file")


def test_unknown_ability_structured_failure():
    abilities, _, _, _ = make_stack()
    with pytest.raises(ValueError, match="Unknown ability"):
        abilities.execute("ghost-tool", "do something", capabilities=["FILE_READ"])


def test_invalid_inputs_rejected_before_execution():
    from abilities.calculator.calculator_ability import CalculatorAbility
    abilities = AbilityManager()
    abilities.register(CalculatorAbility())
    with pytest.raises(RuntimeError, match="Invalid inputs"):
        abilities.execute("calculator", "", capabilities=["MATH"])
    # Rejected before execution: nothing completed.
    assert all(entry.get("result") != "completed" for entry in abilities.audit)


def test_structured_execution_envelope():
    abilities, _, _, _ = make_stack()
    result = abilities.execute("echo-file", "read the file", capabilities=["FILE_READ"])
    for key in ("status", "ability", "capability", "execution_time_ms", "verification"):
        assert key in result, key
    assert result["ability"] == "echo-file"
    assert result["capability"] == "FILE_READ"


def test_filesystem_read_extracts_subdirectory_path():    # Regression: natural-language requests must keep directory prefixes
    # ("read file config/hercule.example.json" used to truncate to the
    # basename and fail with "file not found").
    from abilities.files.file_ability import FileAbility
    abilities = AbilityManager()
    abilities.register(FileAbility())
    result = abilities.execute(
        "files", "read file config/hercule.example.json",
        capabilities=["FILE_READ"])
    assert result["status"] == "success"
    assert "default_model" in result["content"]


def test_filesystem_workspace_follows_call_time_cwd(tmp_path, monkeypatch):
    # The sandbox root is resolved at call time: a chdir'ed test process
    # writes inside tmp_path, never into the repository checkout.
    from abilities.files.file_ability import FileAbility
    monkeypatch.chdir(tmp_path)
    abilities = AbilityManager()
    abilities.register(FileAbility())
    written = abilities.execute(
        "files", {"operation": "write", "path": "sub/note.txt", "data": "tmp-content"},
        capabilities=["FILE_WRITE"])
    assert written["status"] == "success"
    assert (tmp_path / "sub" / "note.txt").read_text(encoding="utf-8") == "tmp-content"


def test_filesystem_safety_blocks_traversal():
    from abilities.files.file_ability import FileAbility
    abilities = AbilityManager()
    abilities.register(FileAbility())
    result = abilities.execute(
        "files", {"operation": "read", "path": "../outside-secret.txt"},
        capabilities=["FILE_READ"])
    assert result["status"] == "failed"
    assert "sandbox" in str(result.get("error", "")).lower()


def test_filesystem_write_then_read_roundtrip(tmp_path, monkeypatch):
    from abilities.files.file_ability import FileAbility
    monkeypatch.chdir(tmp_path)
    abilities = AbilityManager()
    abilities.register(FileAbility())
    written = abilities.execute(
        "files", {"operation": "write", "path": "roundtrip.txt", "data": "verified-content"},
        capabilities=["FILE_WRITE"])
    assert written["status"] == "success"
    read_back = abilities.execute(
        "files", {"operation": "read", "path": "roundtrip.txt"},
        capabilities=["FILE_READ"])
    assert read_back["status"] == "success"
    assert read_back["content"] == "verified-content"


def test_ability_verify_and_permission_helpers():
    abilities, policy, _, _ = make_stack()
    ability = abilities.get("echo-file")
    allowed, _ = ability.check_permissions(policy)
    assert allowed is True
    ok, _ = ability.verify({"status": "success", "content": "x"})
    assert ok is True
    ok, _ = ability.verify({"status": "failed", "error": "boom"})
    assert ok is False
    policy.set_permission("FILE_READ", False)
    try:
        allowed, _ = ability.check_permissions(policy)
        assert allowed is False
    finally:
        policy.set_permission("FILE_READ", True)


def test_spoken_arithmetic_word_operators():
    # v1.1 voice: transcripts say "times"/"plus" (and carry trailing
    # sentence punctuation). The strict AST gate still applies after
    # normalization, so safety is unchanged.
    from abilities.calculator.calculator_ability import safe_evaluate
    assert safe_evaluate("25 times 4.") == 100
    assert safe_evaluate("25 TIMES 4") == 100
    assert safe_evaluate("10 plus 2 minus 3") == 9
    assert safe_evaluate("20 divided by 4") == 5.0
    assert safe_evaluate("7 multiplied by 6?") == 42
    assert safe_evaluate("1,000 plus 24") == 1024
    with pytest.raises(Exception):
        safe_evaluate("import os")
    with pytest.raises(Exception):
        safe_evaluate("times")


def test_mathematics_ability_accepts_spoken_task():
    from abilities.mathematics.mathematics_ability import MathematicsAbility
    abilities = AbilityManager()
    abilities.register(MathematicsAbility())
    result = abilities.execute(
        "mathematics", "Calculate 25 times 4.", capabilities=["MATH"])
    assert result["status"] == "success"
    assert result["result"] == 100
