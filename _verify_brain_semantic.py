"""Verify Brain.configure_semantic() end-to-end wiring."""
import sys, os, traceback

RESULT = r"c:\Users\hp\HERCULE\_verify_brain_semantic.txt"

def log(msg):
    with open(RESULT, "a", encoding="utf-8") as f:
        f.write(msg + "\n")
        f.flush()
    print(msg)

if __name__ == "__main__":
    with open(RESULT, "w", encoding="utf-8") as f:
        f.write("=== Brain.configure_semantic() verification ===\n")
    try:
        # 1. Build stack via RuntimeInitializer
        log("1. Building RuntimeInitializer stack...")
        sys.path.insert(0, r"c:\Users\hp\HERCULE")
        from runtime.initializer import RuntimeInitializer
        services = RuntimeInitializer().initialize()
        brain = services["brain"]
        abilities = services["abilities"]
        policy = getattr(abilities, "policy", None)
        log(f"   OK: brain={type(brain).__name__}, abilities={type(abilities).__name__}, policy={type(policy).__name__ if policy else None}")

        # 2. Build a mock model + SemanticCapabilityProposer
        log("2. Building SemanticCapabilityProposer with mock model...")
        from tests.support_semantic import SemanticMockModel, payload, entry
        from cognition.capabilities.semantic import SemanticCapabilityProposer
        from cognition.capabilities.capability import Capability

        mock_model = SemanticMockModel(
            script=[
                ("crashes", payload(
                    entry("SYSTEM_OBSERVE", 0.92, "user asks about application crashes", True),
                    entry("FILE_READ", 0.70, "may need to inspect log files", False),
                )),
                ("Read this file", payload(
                    entry("FILE_READ", 0.98, "direct file read request", True),
                )),
            ],
            default="[]",
        )
        allowed = [c.value for c in Capability]

        def deterministic_fn(task, ctx, untrusted):
            from cognition.capabilities.inference import infer_capabilities
            return infer_capabilities(task)

        proposer = SemanticCapabilityProposer(
            model=mock_model,
            router=None,
            prompt_manager=None,
            allowed_capabilities=allowed,
            enabled=True,
            required=False,
            shadow=False,
            min_confidence=0.5,
            low_confidence="retain-optional",
            max_retries=1,
            timeout_s=0.0,
            deterministic_fn=deterministic_fn,
        )
        log(f"   OK: proposer={type(proposer).__name__}, enabled={proposer.enabled}")

        # 3. Call brain.configure_semantic()
        log("3. Calling brain.configure_semantic(mode='hybrid', enabled=True)...")
        result = brain.configure_semantic(
            proposer=proposer,
            mode="hybrid",
            enabled=True,
            min_confidence=0.5,
            max_retries=1,
        )
        log(f"   OK: chainable returned brain -> {result is brain}")
        log(f"   OK: brain._semantic_config.mode = {getattr(brain, '_semantic_config', None) and brain._semantic_config.mode}")
        log(f"   OK: brain._semantic_config.enabled = {getattr(brain, '_semantic_config', None) and brain._semantic_config.enabled}")

        # 4. Verify Planner received the configuration
        log("4. Verifying Planner.configure_semantic was called...")
        planner = brain.authoritative_planner
        log(f"   OK: planner._semantic_proposer is proposer -> {getattr(planner, '_semantic_proposer', None) is proposer}")
        log(f"   OK: planner._semantic_enabled = {getattr(planner, '_semantic_enabled', None)}")
        log(f"   OK: planner._semantic_mode = {getattr(planner, '_semantic_mode', None)}")

        # 5. Test implicit SYSTEM_OBSERVE case via create_capable_plan
        log("5. Testing planner.create_capable_plan('Inspect why my application crashes')...")
        goal = "Inspect why my application crashes"
        plan = planner.create_capable_plan(goal, [goal], semantic=None, proposer=None)
        log(f"   OK: plan has {len(plan)} steps")
        step0 = plan[0]
        log(f"   OK: step0.required_capabilities = {step0.get('required_capabilities', [])}")
        log(f"   OK: step0.optional_capabilities = {step0.get('optional_capabilities', [])}")
        report = step0.get("semantic_report", {})
        log(f"   OK: semantic_report.mode = {report.get('mode')}")
        log(f"   OK: semantic_report.final = {report.get('final')}")
        log(f"   OK: semantic_report.optional = {report.get('optional')}")
        log(f"   OK: semantic_report.fallback_used = {report.get('fallback_used')}")
        log(f"   OK: semantic_report.semantic_count = {len(report.get('semantic', []))}")
        log(f"   OK: semantic_report.deterministic_count = {len(report.get('deterministic', []))}")
        log(f"   OK: semantic_report.accepted_count = {len(report.get('accepted', []))}")
        log(f"   OK: semantic_report.rejected_count = {len(report.get('rejected', []))}")

        # Assertions
        required_caps = set(step0.get("required_capabilities", []))
        assert "SYSTEM_OBSERVE" in required_caps, f"Expected SYSTEM_OBSERVE in required_caps, got {required_caps}"
        assert report.get("mode") == "hybrid", f"Expected mode='hybrid', got {report.get('mode')}"
        assert len(report.get("semantic", [])) > 0, "Expected semantic proposals to be generated"
        log("   PASS: implicit SYSTEM_OBSERVE case assertions passed")

        # 6. Test direct FILE_READ case (legacy regression)
        log("6. Testing planner.create_capable_plan('Read this file') (legacy regression)...")
        goal2 = "Read this file"
        plan2 = planner.create_capable_plan(goal2, [goal2], semantic=None, proposer=None)
        step0_2 = plan2[0]
        req2 = set(step0_2.get("required_capabilities", []))
        log(f"   OK: required = {req2}")
        assert "FILE_READ" in req2, f"Expected FILE_READ in {req2}"
        log("   PASS: direct FILE_READ case still works (deterministic + semantic merge)")

        # 7. Test byte-identical legacy path: no configure_semantic at all
        log("7. Testing legacy byte-identical: fresh Planner without configure_semantic...")
        from cognition.planner.planner import Planner
        fresh_planner = Planner()
        plan_legacy = fresh_planner.create_capable_plan(goal2, [goal2])
        step_legacy = plan_legacy[0]
        req_legacy = set(step_legacy.get("required_capabilities", []))
        log(f"   OK: legacy required = {req_legacy}")
        report_legacy = step_legacy.get("semantic_report", {})
        log(f"   OK: legacy semantic_report.mode = {report_legacy.get('mode', 'deterministic (default)')}")
        assert "FILE_READ" in req_legacy
        assert report_legacy.get("mode", "deterministic") in ("deterministic", None)
        log("   PASS: fresh Planner without configure_semantic stays deterministic-only")

        log("\n=== ALL CHECKS PASSED ===")

    except Exception as e:
        log(f"\nFAIL: {e}")
        tb = traceback.format_exc()
        log(tb)
        sys.exit(1)
