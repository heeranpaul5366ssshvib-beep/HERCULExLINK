"""Tests for P3 Approved Automation: Multi-step automation plans."""

from __future__ import annotations

import os
import tempfile
import pytest
from pathlib import Path

from change_proposals import (
    ChangeProposal,
    ChangeOperation,
    ProposalState,
    ChangeErrorCode,
    AutomationPlan,
    AutomationStep,
    AutomationState,
    AutomationStopPolicy,
    AutomationErrorCode,
)
from change_proposal_manager import ChangeProposalManager, AutomationPlanManager
from workspace_manager import WorkspaceManager, create_workspace_manager


class TestAutomationPlanModel:
    """Tests for AutomationPlan data model."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.workspace = Path(self.temp_dir) / "workspace"
        self.workspace.mkdir(parents=True)
        (self.workspace / "existing.txt").write_text("original content")

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_plan_creation_basic(self):
        """Test basic plan creation and hash computation."""
        wm = WorkspaceManager()
        wm.select_workspace(str(self.workspace))
        
        plan = AutomationPlan(
            plan_id="plan-123",
            name="Test Plan",
            workspace_root=str(self.workspace),
            workspace_name="test",
        )
        
        assert plan.plan_id == "plan-123"
        assert plan.name == "Test Plan"
        assert plan.state == "draft"
        assert plan.plan_hash != ""
        assert plan.verify_integrity()

    def test_plan_serialization_roundtrip(self):
        """Test plan serialization and deserialization."""
        plan = AutomationPlan(
            plan_id="plan-456",
            name="Roundtrip Plan",
            description="Test description",
            workspace_root=str(self.workspace),
            workspace_name="test",
            stop_policy="stop_on_failure",
        )
        
        data = plan.to_dict()
        restored = AutomationPlan.from_dict(data)
        
        assert restored.plan_id == plan.plan_id
        assert restored.name == plan.name
        assert restored.description == plan.description
        assert restored.state == plan.state
        assert restored.workspace_root == plan.workspace_root
        assert restored.stop_policy == plan.stop_policy

    def test_plan_hash_integrity(self):
        """Plan hash detects tampering."""
        plan = AutomationPlan(
            plan_id="plan-789",
            name="Hash Test",
            workspace_root=str(self.workspace),
            workspace_name="test",
        )
        
        original_hash = plan.plan_hash
        assert plan.verify_integrity()
        
        # Tamper with name
        plan.name = "Tampered"
        assert not plan.verify_integrity()
        assert plan._compute_hash() != original_hash

    def test_step_serialization(self):
        """Test AutomationStep serialization."""
        step = AutomationStep(
            step_id="step-1",
            proposal_id="prop-1",
            order=0,
            description="First step",
        )
        
        # Test it can be included in plan
        plan = AutomationPlan(
            plan_id="plan-step",
            name="Step Plan",
            workspace_root=str(self.workspace),
            workspace_name="test",
            steps=[step],
        )
        
        data = plan.to_dict()
        assert len(data["steps"]) == 1
        assert data["steps"][0]["step_id"] == "step-1"
        assert data["steps"][0]["proposal_id"] == "prop-1"


class TestAutomationPlanManager:
    """Tests for AutomationPlanManager lifecycle."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.workspace = Path(self.temp_dir) / "workspace"
        self.workspace.mkdir(parents=True)
        (self.workspace / "file1.txt").write_text("content1")
        (self.workspace / "file2.txt").write_text("content2")
        
        self.wm = WorkspaceManager()
        self.wm.select_workspace(str(self.workspace))
        self.cpm = ChangeProposalManager(self.wm)
        self.apm = AutomationPlanManager(self.cpm)

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # ================================================================
    # A. Plan Creation and Validation
    # ================================================================

    def test_create_plan_begins_in_draft(self):
        """Create plan begins in DRAFT state."""
        plan = self.apm.create_plan(
            name="Test Plan",
            proposal_ids=[],
        )
        assert plan.state == "draft"
        assert plan.plan_id in self.apm._plans

    def test_create_plan_with_proposals(self):
        """Create plan with existing proposals."""
        # Create proposals first
        prop1 = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="new1.txt",
            content="content1",
        )
        prop2 = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="new2.txt",
            content="content2",
        )
        
        plan = self.apm.create_plan(
            name="Multi-step Plan",
            proposal_ids=[prop1.proposal_id, prop2.proposal_id],
        )
        
        assert len(plan.steps) == 2
        assert plan.steps[0].proposal_id == prop1.proposal_id
        assert plan.steps[1].proposal_id == prop2.proposal_id
        assert plan.steps[0].order == 0
        assert plan.steps[1].order == 1

    def test_plan_validation_validates_all_proposals(self):
        """Plan validation validates all proposals."""
        prop1 = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="valid1.txt",
            content="content1",
        )
        prop2 = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="valid2.txt",
            content="content2",
        )
        
        plan = self.apm.create_plan(
            name="Valid Plan",
            proposal_ids=[prop1.proposal_id, prop2.proposal_id],
        )
        
        validated = self.apm.validate_plan(plan.plan_id)
        assert validated.state == "validated"

    def test_plan_validation_fails_on_bad_proposal(self):
        """Plan validation fails if any proposal is invalid."""
        prop1 = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="valid.txt",
            content="content1",
        )
        # Create a proposal that will fail validation (sensitive file)
        prop2 = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path=".env",
            content="SECRET=123",
        )
        
        plan = self.apm.create_plan(
            name="Invalid Plan",
            proposal_ids=[prop1.proposal_id, prop2.proposal_id],
        )
        
        validated = self.apm.validate_plan(plan.plan_id)
        assert validated.state == "failed"
        assert validated.error_code in ("sensitive_file", "execution_failed")

    def test_plan_validation_fails_on_missing_proposal(self):
        """Plan validation fails if proposal doesn't exist."""
        plan = self.apm.create_plan(
            name="Missing Prop Plan",
            proposal_ids=["nonexistent-prop-id"],
        )
        
        validated = self.apm.validate_plan(plan.plan_id)
        assert validated.state == "failed"
        assert validated.error_code == "execution_failed"

    def test_plan_with_no_steps_fails(self):
        """Plan with no steps fails validation."""
        plan = self.apm.create_plan(
            name="Empty Plan",
            proposal_ids=[],
        )
        
        validated = self.apm.validate_plan(plan.plan_id)
        assert validated.state == "failed"
        assert validated.error_code == "no_proposals"

    # ================================================================
    # B. Plan Approval/Rejection/Cancellation
    # ================================================================

    def test_plan_approval_approves_all_proposals(self):
        """Approving a plan approves all its proposals."""
        prop1 = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="approved1.txt",
            content="content1",
        )
        prop2 = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="approved2.txt",
            content="content2",
        )
        
        plan = self.apm.create_plan(
            name="Approval Plan",
            proposal_ids=[prop1.proposal_id, prop2.proposal_id],
        )
        self.apm.validate_plan(plan.plan_id)
        self.apm.submit_for_approval(plan.plan_id)
        
        approved = self.apm.approve(plan.plan_id)
        
        assert approved.state == "approved"
        # Check proposals were approved
        p1 = self.cpm.get_proposal(prop1.proposal_id)
        p2 = self.cpm.get_proposal(prop2.proposal_id)
        assert p1.state == "approved"
        assert p2.state == "approved"

    def test_plan_rejection_rejects_all_proposals(self):
        """Rejecting a plan rejects all its proposals."""
        prop1 = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="rejected1.txt",
            content="content1",
        )
        prop2 = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="rejected2.txt",
            content="content2",
        )
        
        plan = self.apm.create_plan(
            name="Rejection Plan",
            proposal_ids=[prop1.proposal_id, prop2.proposal_id],
        )
        self.apm.validate_plan(plan.plan_id)
        self.apm.submit_for_approval(plan.plan_id)
        
        rejected = self.apm.reject(plan.plan_id)
        
        assert rejected.state == "rejected"
        # Check proposals were rejected
        p1 = self.cpm.get_proposal(prop1.proposal_id)
        p2 = self.cpm.get_proposal(prop2.proposal_id)
        assert p1.state == "rejected"
        assert p2.state == "rejected"

    def test_plan_cancellation_cancels_all_proposals(self):
        """Cancelling a plan cancels all its proposals."""
        prop1 = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="cancelled1.txt",
            content="content1",
        )
        
        plan = self.apm.create_plan(
            name="Cancellation Plan",
            proposal_ids=[prop1.proposal_id],
        )
        self.apm.validate_plan(plan.plan_id)
        
        cancelled = self.apm.cancel(plan.plan_id)
        
        assert cancelled.state == "cancelled"
        p1 = self.cpm.get_proposal(prop1.proposal_id)
        assert p1.state == "cancelled"

    def test_rejected_plan_cannot_be_approved(self):
        """A rejected plan cannot be approved."""
        prop1 = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="reject_then_approve.txt",
            content="content",
        )
        
        plan = self.apm.create_plan(
            name="Reject Then Approve",
            proposal_ids=[prop1.proposal_id],
        )
        self.apm.validate_plan(plan.plan_id)
        self.apm.submit_for_approval(plan.plan_id)
        self.apm.reject(plan.plan_id)
        
        with pytest.raises(ValueError, match="not in approvable state"):
            self.apm.approve(plan.plan_id)

    # ================================================================
    # C. Plan Execution (Dry-run and Real)
    # ================================================================

    def test_dry_run_validates_without_mutation(self):
        """Dry-run validates proposals without mutating filesystem."""
        prop1 = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="dryrun1.txt",
            content="dry run content",
        )
        prop2 = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="dryrun2.txt",
            content="dry run content 2",
        )
        
        plan = self.apm.create_plan(
            name="Dry-run Plan",
            proposal_ids=[prop1.proposal_id, prop2.proposal_id],
        )
        self.apm.validate_plan(plan.plan_id)
        self.apm.submit_for_approval(plan.plan_id)
        self.apm.approve(plan.plan_id)
        
        # Dry-run
        result = self.apm.execute_plan(plan.plan_id, dry_run=True)
        
        assert result.state == "verified"
        # Files should not exist
        assert not (self.workspace / "dryrun1.txt").exists()
        assert not (self.workspace / "dryrun2.txt").exists()
        # Steps should be marked verified
        assert all(s.verified for s in result.steps)

    def test_execute_plan_applies_all_proposals(self):
        """Execute plan applies all approved proposals."""
        prop1 = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="exec1.txt",
            content="exec content 1",
        )
        prop2 = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="exec2.txt",
            content="exec content 2",
        )
        
        plan = self.apm.create_plan(
            name="Execute Plan",
            proposal_ids=[prop1.proposal_id, prop2.proposal_id],
        )
        self.apm.validate_plan(plan.plan_id)
        self.apm.submit_for_approval(plan.plan_id)
        self.apm.approve(plan.plan_id)
        
        result = self.apm.execute_plan(plan.plan_id)
        
        assert result.state == "verified"
        assert (self.workspace / "exec1.txt").exists()
        assert (self.workspace / "exec1.txt").read_text() == "exec content 1"
        assert (self.workspace / "exec2.txt").exists()
        assert (self.workspace / "exec2.txt").read_text() == "exec content 2"
        assert all(s.verified for s in result.steps)

    def test_execute_plan_stop_on_failure(self):
        """STOP_ON_FAILURE stops execution on first failure."""
        # Create a file to edit
        (self.workspace / "edit_me.txt").write_text("original")
        
        prop1 = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="stop1.txt",
            content="content1",
        )
        # This will fail at execution due to stale source
        prop2 = self.cpm.create_proposal(
            operation="edit_text_file",
            source_path="edit_me.txt",
            content="proposed edit",
        )
        prop3 = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="stop3.txt",
            content="content3",
        )
        
        plan = self.apm.create_plan(
            name="Stop on Failure",
            proposal_ids=[prop1.proposal_id, prop2.proposal_id, prop3.proposal_id],
            stop_policy="stop_on_failure",
        )
        self.apm.validate_plan(plan.plan_id)
        self.apm.submit_for_approval(plan.plan_id)
        self.apm.approve(plan.plan_id)
        
        # Modify file externally to cause stale source failure on prop2
        (self.workspace / "edit_me.txt").write_text("externally modified")
        
        result = self.apm.execute_plan(plan.plan_id)
        
        # First should succeed, second fails (stale source), third not executed
        assert result.state == "partially_applied"
        assert (self.workspace / "stop1.txt").exists()
        assert not (self.workspace / "stop3.txt").exists()
        # Check step results
        assert result.steps[0].verified is True
        assert result.steps[1].verified is False
        assert "stale" in result.steps[1].verification_error.lower()
        assert result.steps[2].verified is False  # Not executed due to stop_on_failure

    def test_execute_plan_continue_on_failure(self):
        """CONTINUE_INDEPENDENT_STEPS continues after failure."""
        (self.workspace / "edit_me.txt").write_text("original")
        
        prop1 = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="cont1.txt",
            content="content1",
        )
        prop2 = self.cpm.create_proposal(
            operation="edit_text_file",
            source_path="edit_me.txt",
            content="proposed edit",
        )
        prop3 = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="cont3.txt",
            content="content3",
        )
        
        plan = self.apm.create_plan(
            name="Continue on Failure",
            proposal_ids=[prop1.proposal_id, prop2.proposal_id, prop3.proposal_id],
            stop_policy="continue_independent_steps",
        )
        self.apm.validate_plan(plan.plan_id)
        self.apm.submit_for_approval(plan.plan_id)
        self.apm.approve(plan.plan_id)
        
        # Modify file externally to cause stale source failure on prop2
        (self.workspace / "edit_me.txt").write_text("externally modified")
        
        result = self.apm.execute_plan(plan.plan_id)
        
        # All should be attempted
        assert result.state == "partially_applied"
        assert (self.workspace / "cont1.txt").exists()
        assert (self.workspace / "cont3.txt").exists()
        # Check step results
        assert result.steps[0].verified is True
        assert result.steps[1].verified is False
        assert "stale" in result.steps[1].verification_error.lower()
        assert result.steps[2].verified is True  # Executed despite failure

    def test_execute_unapproved_plan_fails(self):
        """Executing an unapproved plan fails."""
        prop1 = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="unapproved.txt",
            content="content",
        )
        
        plan = self.apm.create_plan(
            name="Unapproved Plan",
            proposal_ids=[prop1.proposal_id],
        )
        self.apm.validate_plan(plan.plan_id)
        self.apm.submit_for_approval(plan.plan_id)
        # Not approved!
        
        with pytest.raises(ValueError, match="not approved"):
            self.apm.execute_plan(plan.plan_id)

    def test_execute_plan_tampering_detected(self):
        """Plan tampering after approval is detected."""
        prop1 = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="tamper.txt",
            content="content",
        )
        
        plan = self.apm.create_plan(
            name="Tamper Plan",
            proposal_ids=[prop1.proposal_id],
        )
        self.apm.validate_plan(plan.plan_id)
        self.apm.submit_for_approval(plan.plan_id)
        self.apm.approve(plan.plan_id)
        
        # Tamper with plan
        plan.name = "Tampered"
        
        result = self.apm.execute_plan(plan.plan_id)
        assert result.state == "failed"
        assert result.error_code == "plan_tampered"

    # ================================================================
    # D. Workspace and Expiration
    # ================================================================

    def test_workspace_change_prevents_execution(self):
        """Workspace change after plan creation prevents execution."""
        prop1 = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="ws_change.txt",
            content="content",
        )
        
        plan = self.apm.create_plan(
            name="Workspace Change",
            proposal_ids=[prop1.proposal_id],
        )
        self.apm.validate_plan(plan.plan_id)
        self.apm.submit_for_approval(plan.plan_id)
        self.apm.approve(plan.plan_id)
        
        # Clear workspace
        self.apm.proposal_manager.workspace_manager.clear_workspace()
        
        result = self.apm.execute_plan(plan.plan_id)
        assert result.state == "failed"
        assert result.error_code == "workspace_escape"

    def test_expired_plan_cannot_execute(self):
        """Expired plan cannot be executed."""
        prop1 = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="expired_plan.txt",
            content="content",
        )
        
        plan = self.apm.create_plan(
            name="Expired Plan",
            proposal_ids=[prop1.proposal_id],
            expires_in=0.001,
        )
        self.apm.validate_plan(plan.plan_id)
        self.apm.submit_for_approval(plan.plan_id)
        self.apm.approve(plan.plan_id)
        
        import time
        time.sleep(0.01)
        
        result = self.apm.execute_plan(plan.plan_id)
        assert result.state == "failed"
        assert result.error_code == "approval_expired"

    def test_plan_expiration_works(self):
        """Plan expiration moves PENDING_APPROVAL to EXPIRED."""
        prop1 = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="expire1.txt",
            content="content",
        )
        
        plan = self.apm.create_plan(
            name="Expiring Plan",
            proposal_ids=[prop1.proposal_id],
            expires_in=0.001,
        )
        self.apm.validate_plan(plan.plan_id)
        self.apm.submit_for_approval(plan.plan_id)
        
        import time
        time.sleep(0.01)
        count = self.apm.expire_stale_plans()
        
        assert count == 1
        plan = self.apm.get_plan(plan.plan_id)
        assert plan.state == "expired"

    # ================================================================
    # E. Verification
    # ================================================================

    def test_verification_detects_content_mismatch(self):
        """Verification detects if file content doesn't match proposal."""
        prop1 = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="verify1.txt",
            content="expected content",
        )
        
        plan = self.apm.create_plan(
            name="Verify Plan",
            proposal_ids=[prop1.proposal_id],
        )
        self.apm.validate_plan(plan.plan_id)
        self.apm.submit_for_approval(plan.plan_id)
        self.apm.approve(plan.plan_id)
        
        result = self.apm.execute_plan(plan.plan_id)
        
        assert result.state == "verified"
        assert result.steps[0].verified is True

    def test_verification_detects_move_result(self):
        """Verification works for move operations."""
        (self.workspace / "move_source.txt").write_text("move me")
        
        prop1 = self.cpm.create_proposal(
            operation="move_or_rename",
            source_path="move_source.txt",
            destination_path="move_dest.txt",
        )
        
        plan = self.apm.create_plan(
            name="Move Verify Plan",
            proposal_ids=[prop1.proposal_id],
        )
        self.apm.validate_plan(plan.plan_id)
        self.apm.submit_for_approval(plan.plan_id)
        self.apm.approve(plan.plan_id)
        
        result = self.apm.execute_plan(plan.plan_id)
        
        assert result.state == "verified"
        assert not (self.workspace / "move_source.txt").exists()
        assert (self.workspace / "move_dest.txt").exists()
        assert (self.workspace / "move_dest.txt").read_text() == "move me"
        assert result.steps[0].verified is True

    # ================================================================
    # F. Audit and State Transitions
    # ================================================================

    def test_plan_audit_trail(self):
        """Plan audit trail records state transitions."""
        prop1 = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="audit.txt",
            content="audit content",
        )
        
        plan = self.apm.create_plan(
            name="Audit Plan",
            proposal_ids=[prop1.proposal_id],
        )
        self.apm.validate_plan(plan.plan_id)
        self.apm.submit_for_approval(plan.plan_id)
        self.apm.approve(plan.plan_id)
        self.apm.execute_plan(plan.plan_id)
        
        trail = self.apm.get_plan_audit_trail(plan.plan_id)
        
        events = [e["event"] for e in trail]
        assert "created" in events
        assert "approved" in events
        assert "executed" in events

    def test_plan_state_transitions_correct(self):
        """Plan follows correct state transitions."""
        prop1 = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="state1.txt",
            content="content",
        )
        
        plan = self.apm.create_plan(
            name="State Plan",
            proposal_ids=[prop1.proposal_id],
        )
        
        assert plan.state == "draft"
        
        self.apm.validate_plan(plan.plan_id)
        assert plan.state == "validated"
        
        self.apm.submit_for_approval(plan.plan_id)
        assert plan.state == "pending_approval"
        
        self.apm.approve(plan.plan_id)
        assert plan.state == "approved"
        
        self.apm.execute_plan(plan.plan_id)
        assert plan.state == "verified"

    # ================================================================
    # G. Mixed Operations
    # ================================================================

    def test_plan_with_mixed_operations(self):
        """Plan can contain create, edit, and move operations."""
        (self.workspace / "edit_target.txt").write_text("original")
        (self.workspace / "move_target.txt").write_text("move me")
        
        prop1 = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="created.txt",
            content="created content",
        )
        prop2 = self.cpm.create_proposal(
            operation="edit_text_file",
            source_path="edit_target.txt",
            content="edited content",
        )
        prop3 = self.cpm.create_proposal(
            operation="move_or_rename",
            source_path="move_target.txt",
            destination_path="moved.txt",
        )
        
        plan = self.apm.create_plan(
            name="Mixed Operations",
            proposal_ids=[prop1.proposal_id, prop2.proposal_id, prop3.proposal_id],
        )
        self.apm.validate_plan(plan.plan_id)
        self.apm.submit_for_approval(plan.plan_id)
        self.apm.approve(plan.plan_id)
        
        result = self.apm.execute_plan(plan.plan_id)
        
        assert result.state == "verified"
        assert (self.workspace / "created.txt").read_text() == "created content"
        assert (self.workspace / "edit_target.txt").read_text() == "edited content"
        assert not (self.workspace / "move_target.txt").exists()
        assert (self.workspace / "moved.txt").read_text() == "move me"
        assert all(s.verified for s in result.steps)


class TestP3Security:
    """Security-focused tests for P3 automation."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.workspace = Path(self.temp_dir) / "workspace"
        self.workspace.mkdir(parents=True)
        (self.workspace / "test.txt").write_text("test")
        
        self.wm = WorkspaceManager()
        self.wm.select_workspace(str(self.workspace))
        self.cpm = ChangeProposalManager(self.wm)
        self.apm = AutomationPlanManager(self.cpm)

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_traversal_in_plan_rejected(self):
        """Path traversal in any proposal is rejected."""
        prop1 = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="../outside.txt",
            content="traversal",
        )
        
        plan = self.apm.create_plan(
            name="Traversal Plan",
            proposal_ids=[prop1.proposal_id],
        )
        
        validated = self.apm.validate_plan(plan.plan_id)
        assert validated.state == "failed"
        assert validated.error_code in ("traversal", "invalid_path")

    def test_sensitive_file_in_plan_rejected(self):
        """Sensitive file in any proposal is rejected."""
        prop1 = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path=".env",
            content="SECRET=123",
        )
        
        plan = self.apm.create_plan(
            name="Sensitive Plan",
            proposal_ids=[prop1.proposal_id],
        )
        
        validated = self.apm.validate_plan(plan.plan_id)
        assert validated.state == "failed"
        assert validated.error_code == "sensitive_file"

    def test_absolute_path_in_plan_rejected(self):
        """Absolute path outside workspace is rejected."""
        outside = Path(tempfile.mkdtemp()) / "outside.txt"
        
        prop1 = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path=str(outside),
            content="outside",
        )
        
        plan = self.apm.create_plan(
            name="Absolute Path Plan",
            proposal_ids=[prop1.proposal_id],
        )
        
        validated = self.apm.validate_plan(plan.plan_id)
        assert validated.state == "failed"
        assert validated.error_code in ("traversal", "invalid_path")

    def test_similar_prefix_in_plan_rejected(self):
        """Similar-prefix path is rejected."""
        similar = Path(self.temp_dir) / "workspace-other"
        similar.mkdir()
        
        prop1 = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path=str(similar / "file.txt"),
            content="similar",
        )
        
        plan = self.apm.create_plan(
            name="Similar Prefix Plan",
            proposal_ids=[prop1.proposal_id],
        )
        
        validated = self.apm.validate_plan(plan.plan_id)
        assert validated.state == "failed"
        assert validated.error_code == "traversal"

    def test_proposal_tampering_after_approval_detected(self):
        """Proposal tampering after plan approval is detected at execution."""
        prop1 = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="tamper_prop.txt",
            content="original",
        )
        
        plan = self.apm.create_plan(
            name="Prop Tamper Plan",
            proposal_ids=[prop1.proposal_id],
        )
        self.apm.validate_plan(plan.plan_id)
        self.apm.submit_for_approval(plan.plan_id)
        self.apm.approve(plan.plan_id)
        
        # Tamper with proposal after plan approval
        prop1.content = "tampered"
        
        result = self.apm.execute_plan(plan.plan_id)
        assert result.state == "failed"
        # The proposal's own integrity check should catch this
        assert result.steps[0].verified is False
        assert "integrity" in result.steps[0].verification_error.lower() or "hash" in result.steps[0].verification_error.lower()

    def test_stale_source_detection_at_execution(self):
        """Stale source detection works at execution time."""
        (self.workspace / "stale_edit.txt").write_text("original")
        
        prop1 = self.cpm.create_proposal(
            operation="edit_text_file",
            source_path="stale_edit.txt",
            content="proposed edit",
        )
        
        plan = self.apm.create_plan(
            name="Stale Source Plan",
            proposal_ids=[prop1.proposal_id],
        )
        self.apm.validate_plan(plan.plan_id)
        self.apm.submit_for_approval(plan.plan_id)
        self.apm.approve(plan.plan_id)
        
        # Modify file externally
        (self.workspace / "stale_edit.txt").write_text("externally modified")
        
        result = self.apm.execute_plan(plan.plan_id)
        
        assert result.state == "partially_applied" or result.state == "failed"
        assert result.steps[0].verified is False
        assert "stale" in result.steps[0].verification_error.lower()


class TestPlatformSpecific:
    """Platform-specific tests."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.workspace = Path(self.temp_dir) / "workspace"
        self.workspace.mkdir(parents=True)
        (self.workspace / "test.txt").write_text("test")
        
        self.wm = WorkspaceManager()
        self.wm.select_workspace(str(self.workspace))
        self.cpm = ChangeProposalManager(self.wm)
        self.apm = AutomationPlanManager(self.cpm)

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @pytest.mark.skipif(os.name != "nt", reason="Windows junction test")
    def test_windows_junction_in_plan_rejected(self):
        """Windows junction pointing outside workspace is detected in plan."""
        outside = Path(tempfile.mkdtemp()) / "outside"
        outside.mkdir()
        (outside / "secret.txt").write_text("secret")
        
        link_path = Path(self.temp_dir) / "workspace" / "junction_to_outside"
        import os
        os.system(f'mklink /J "{link_path}" "{outside}"')
        
        prop1 = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="junction_to_outside/secret.txt",
            content="secret",
        )
        
        plan = self.apm.create_plan(
            name="Junction Plan",
            proposal_ids=[prop1.proposal_id],
        )
        
        validated = self.apm.validate_plan(plan.plan_id)
        assert validated.state == "failed"
        assert validated.error_code in ("symlink_escape", "traversal", "workspace_escape")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])