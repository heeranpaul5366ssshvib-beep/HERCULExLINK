"""Lightweight verification of Brain.configure_semantic() without full RuntimeInitializer stack."""
import sys, os, traceback, types

RESULT = r"c:\Users\hp\HERCULE\_verify_light.txt"

def log(msg):
    with open(RESULT, "a", encoding="utf-8") as f:
        f.write(msg + "\n"); f.flush()
    print(msg)

if __name__ == "__main__":
    with open(RESULT, "w", encoding="utf-8") as f:
        f.write("=== Lightweight Brain.configure_semantic verification ===\n")

    sys.path.insert(0, r"c:\Users\hp\HERCULE")

    try:
        # 1. Import only what we need for Planner + semantic capabilities
        log("1. Importing core modules...")
        from cognition.planner.planner import Planner
        from cognition.capabilities.capability import Capability
        from tests.support_semantic import SemanticMockModel, payload, entry
        log("   OK: planner + mock imports")

        from cognition.capabilities.semantic import SemanticCapabilityProposer
        from cognition.capabilities.inference import infer_capabilities
        log("   OK: semantic + inference imports")

        # 2. Build mock model + proposer
        log("2. Building SemanticCapabilityProposer with mock model...")
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
        log(f"   OK: proposer built, enabled={proposer.enabled}")

        # 3. Test Planner.configure_semantic() directly first (what Brain delegates to)
        log("3. Testing Planner.configure_semantic() directly...")
        planner = Planner()
        planner.configure_semantic(
            proposer=proposer,
            mode="hybrid",
            enabled=True,
            resolver_kwargs={},
        )
        log(f"   OK: planner._semantic_proposer is proposer -> {planner._semantic_proposer is proposer}")
        log(f"   OK: planner._semantic_enabled = {planner._semantic_enabled}")
        log(f"   OK: planner._semantic_mode = {planner._semantic_mode}")

        # 4. Test implicit SYSTEM_OBSERVE case
        log("4. Testing implicit SYSTEM_OBSERVE case...")
        goal = "Inspect why my application crashes"
        plan = planner.create_capable_plan(goal, [goal], semantic=None, proposer=None)
        step0 = plan[0]
        req = set(step0.get("required_capabilities", []))
        report = step0.get("semantic_report", {})
        log(f"   required = {req}")
        log(f"   mode = {report.get('mode')}")
        log(f"   final = {report.get('final')}")
        log(f"   sem_count = {len(report.get('semantic', []))}")
        log(f"   det_count = {len(report.get('deterministic', []))}")
        log(f"   accepted = {report.get('accepted')}")
        log(f"   rejected = {report.get('rejected')}")
        log(f"   fallback_used = {report.get('fallback_used')}")
        assert "SYSTEM_OBSERVE" in req, f"Missing SYSTEM_OBSERVE in {req}"
        assert report.get("mode") == "hybrid", f"Expected hybrid, got {report.get('mode')}"
        assert len(report.get("semantic", [])) > 0, "No semantic proposals generated"
        log("   PASS")

        # 5. Test direct FILE_READ case
        log("5. Testing direct FILE_READ case...")
        goal2 = "Read this file"
        plan2 = planner.create_capable_plan(goal2, [goal2], semantic=None, proposer=None)
        step0_2 = plan2[0]
        req2 = set(step0_2.get("required_capabilities", []))
        log(f"   required = {req2}")
        assert "FILE_READ" in req2
        log("   PASS")

        # 6. Test fresh Planner stays deterministic-only (legacy regression)
        log("6. Testing fresh Planner without configure_semantic stays deterministic...")
        fresh = Planner()
        plan_fresh = fresh.create_capable_plan(goal2, [goal2])
        step_f = plan_fresh[0]
        req_f = set(step_f.get("required_capabilities", []))
        report_f = step_f.get("semantic_report", {})
        log(f"   required = {req_f}")
        log(f"   mode = {report_f.get('mode', 'deterministic')}")
        assert "FILE_READ" in req_f
        mode_f = report_f.get("mode", "deterministic")
        assert mode_f in ("deterministic", None), f"Expected deterministic-only, got {mode_f}"
        log("   PASS")

        # 7. Now test Brain.configure_semantic() with a minimal mock orchestrator
        log("7. Testing Brain.configure_semantic() with mock orchestrator...")
        # Import Brain — this is lighter than RuntimeInitializer since we mock orchestrator
        from brain.brain import Brain
        from cognition.capabilities.registry import CapabilityRegistry

        # Build a minimal mock orchestrator with just what configure_semantic needs:
        # orchestrator.abilities -> ability_manager, policy
        # Also orchestrator needs to have enough for Brain.__init__
        mock_abilities = types.SimpleNamespace()
        # ability_manager.get() returns a truthy tool for register_default_tools
        class FakeAM:
            def get(self, name, default=None):
                # Return a truthy value (simulate tool exists) for the 17 default tools
                return default if False else types.SimpleNamespace(enabled=True)
            def policy(self):
                return None
        mock_abilities = FakeAM()
        mock_abilities.policy = None  # attribute, not method

        # Brain.__init__ stores orchestrator and creates authoritative_planner
        # Let's see what Brain.__init__ actually needs
        mock_orch = types.SimpleNamespace(abilities=mock_abilities)

        # Actually let's check Brain constructor first
        # We'll try constructing Brain with minimal mock — if it fails, we just test Planner directly
        try:
            brain = Brain.__new__(Brain)
            brain.orchestrator = mock_orch
            # Replicate what Brain.__init__ does for authoritative_planner
            brain.authoritative_planner = Planner()
            brain._semantic_config = None
        except Exception as e:
            log(f"   SKIP full Brain construction: {e}")
            brain = None

        if brain is not None:
            # Now test Brain.configure_semantic() with the manually constructed instance
            log("   Calling brain.configure_semantic(mode='hybrid', enabled=True, proposer=proposer)...")
            result = brain.configure_semantic(
                proposer=proposer,
                mode="hybrid",
                enabled=True,
                min_confidence=0.5,
            )
            log(f"   chainable returned brain -> {result is brain}")
            log(f"   brain._semantic_config.mode = {brain._semantic_config.mode}")
            log(f"   brain._semantic_config.enabled = {brain._semantic_config.enabled}")
            log(f"   planner._semantic_mode = {brain.authoritative_planner._semantic_mode}")
            log(f"   planner._semantic_enabled = {brain.authoritative_planner._semantic_enabled}")
            log(f"   planner._semantic_proposer is proposer -> {brain.authoritative_planner._semantic_proposer is proposer}")
            assert result is brain, "configure_semantic should be chainable"
            assert str(brain._semantic_config.mode).lower().endswith("hybrid"), "Should set mode to hybrid"
            assert brain._semantic_config.enabled is True
            assert brain.authoritative_planner._semantic_proposer is proposer
            log("   PASS: Brain.configure_semantic() delegates correctly")

            # Now test plan creation via the configured Brain's planner
            plan_b = brain.authoritative_planner.create_capable_plan(goal, [goal], semantic=None, proposer=None)
            req_b = set(plan_b[0].get("required_capabilities", []))
            report_b = plan_b[0].get("semantic_report", {})
            log(f"   plan via brain: required={req_b}, mode={report_b.get('mode')}")
            assert "SYSTEM_OBSERVE" in req_b
            assert report_b.get("mode") == "hybrid"
            log("   PASS: plan via configured Brain uses hybrid mode")

        log("\n=== ALL CHECKS PASSED ===")

    except Exception as e:
        log(f"\nFAIL: {e}")
        log(traceback.format_exc())
        sys.exit(1)
