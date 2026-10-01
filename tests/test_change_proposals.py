"""Tests for P2 Change Proposals: Safe Creation and Change Previews."""

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
    ChangePreview,
)
from change_proposal_manager import ChangeProposalManager
from workspace_manager import WorkspaceManager, create_workspace_manager
from workspace_manager import _is_sensitive_file, _matches_sensitive


class TestChangeProposalModel:
    """Tests for ChangeProposal data model."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.workspace = Path(self.temp_dir) / "workspace"
        self.workspace.mkdir(parents=True)
        (self.workspace / "existing.txt").write_text("original content")
        (self.workspace / ".env").write_text("SECRET=123")

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_proposal_creation_basic(self):
        """Test basic proposal creation and hash computation."""
        wm = WorkspaceManager()
        wm.select_workspace(".")
        
        proposal = ChangeProposal(
            proposal_id="test-123",
            operation="create_text_file",
            workspace_root=str(Path.cwd()),
            workspace_name="test",
            destination_path="new.txt",
            content="hello world",
        )
        
        assert proposal.proposal_id == "test-123"
        assert proposal.operation == "create_text_file"
        assert proposal.state == "draft"
        assert proposal.proposal_hash != ""
        assert proposal.verify_integrity()

    def test_proposal_serialization_roundtrip(self):
        """Test proposal serialization and deserialization."""
        proposal = ChangeProposal(
            proposal_id="test-456",
            operation="edit_text_file",
            workspace_root=str(Path.cwd()),
            workspace_name="test",
            source_path="existing.txt",
            content="new content",
        )
        
        data = proposal.to_dict()
        restored = ChangeProposal.from_dict(data)
        
        assert restored.proposal_id == proposal.proposal_id
        assert restored.operation == proposal.operation
        assert restored.state == proposal.state
        assert restored.workspace_root == proposal.workspace_root
        assert restored.source_path == proposal.source_path
        assert restored.content == proposal.content

    def test_proposal_hash_integrity(self):
        """Proposal hash detects tampering."""
        proposal = ChangeProposal(
            proposal_id="test-789",
            operation="create_text_file",
            workspace_root=str(Path.cwd()),
            workspace_name="test",
            destination_path="new.txt",
            content="original",
        )
        
        original_hash = proposal.proposal_hash
        assert proposal.verify_integrity()
        
        # Tamper with content
        proposal.content = "tampered"
        assert not proposal.verify_integrity()
        assert proposal._compute_hash() != original_hash


class TestChangeProposalManager:
    """Tests for ChangeProposalManager lifecycle."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.workspace = Path(self.temp_dir) / "workspace"
        self.workspace.mkdir(parents=True)
        (self.workspace / "existing.txt").write_text("original content")
        (self.workspace / ".env").write_text("SECRET=123")
        (self.workspace / "subdir").mkdir(parents=True)
        (self.workspace / "subdir" / "nested.txt").write_text("nested content")
        
        self.wm = WorkspaceManager()
        self.wm.select_workspace(str(self.workspace))
        self.cpm = ChangeProposalManager(self.wm)

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # ================================================================
    # A. Proposal Lifecycle Tests
    # ================================================================

    def test_create_proposal_begins_in_draft(self):
        """Create proposal begins in DRAFT state."""
        proposal = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="new.txt",
            content="hello",
        )
        assert proposal.state == "draft"
        assert proposal.proposal_id in self.cpm._proposals

    def test_proposal_preview_available_before_approval(self):
        """Proposal preview is available before approval."""
        proposal = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="preview.txt",
            content="preview content",
        )
        
        preview = self.cpm.get_proposal_preview(proposal.proposal_id)
        assert preview is not None
        assert preview.operation == "create_text_file"
        assert preview.content_preview == "preview content"
        assert not preview.exists

    def test_rejection_produces_rejected_status(self):
        """Rejection produces REJECTED status."""
        proposal = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="to_reject.txt",
            content="reject me",
        )
        
        self.cpm.submit_for_approval(proposal.proposal_id)
        rejected = self.cpm.reject(proposal.proposal_id)
        
        assert rejected.state == "rejected"
        assert rejected.rejected_at is not None

    def test_rejection_does_not_mutate_filesystem(self):
        """Rejection does not mutate the filesystem."""
        proposal = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="should_not_exist.txt",
            content="rejected content",
        )
        self.cpm.submit_for_approval(proposal.proposal_id)
        self.cpm.reject(proposal.proposal_id)
        
        # File should not exist
        target = Path(self.workspace) / "should_not_exist.txt"
        assert not target.exists()

    def test_cancellation_does_not_mutate_filesystem(self):
        """Cancellation does not mutate the filesystem."""
        proposal = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="cancelled.txt",
            content="cancelled content",
        )
        self.cpm.cancel(proposal.proposal_id)
        
        target = Path(self.workspace) / "cancelled.txt"
        assert not target.exists()

    def test_only_approved_proposal_may_apply(self):
        """Only an approved proposal may apply."""
        proposal = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="needs_approval.txt",
            content="need approval",
        )
        
        # Try to apply without approval - should fail
        with pytest.raises(ValueError, match="not approved"):
            self.cpm.apply(proposal.proposal_id)

    def test_proposal_cannot_apply_twice(self):
        """A proposal cannot apply twice."""
        proposal = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="apply_once.txt",
            content="apply once",
        )
        self.cpm.submit_for_approval(proposal.proposal_id)
        self.cpm.approve(proposal.proposal_id)
        
        # First apply
        applied = self.cpm.apply(proposal.proposal_id)
        assert applied.state == "applied"
        
        # Second apply should fail
        with pytest.raises(ValueError, match="not approved"):
            self.cpm.apply(proposal.proposal_id)

    def test_rejected_proposal_cannot_be_approved(self):
        """An already rejected proposal cannot be approved."""
        proposal = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="rejected.txt",
            content="rejected",
        )
        self.cpm.submit_for_approval(proposal.proposal_id)
        self.cpm.reject(proposal.proposal_id)
        
        with pytest.raises(ValueError, match="not in approvable state"):
            self.cpm.approve(proposal.proposal_id)

    def test_expired_proposal_cannot_be_approved(self):
        """An expired proposal cannot be approved."""
        proposal = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="expired.txt",
            content="expired",
            expires_in=0.001,  # Expire immediately
        )
        self.cpm.submit_for_approval(proposal.proposal_id)
        
        # Wait for expiration
        import time
        time.sleep(0.01)
        self.cpm.expire_stale_proposals()
        
        with pytest.raises(ValueError, match="not in approvable state"):
            self.cpm.approve(proposal.proposal_id)

    def test_proposal_ids_are_unique(self):
        """Proposal IDs are unique."""
        ids = set()
        for _ in range(100):
            proposal = self.cpm.create_proposal(
                operation="create_text_file",
                destination_path=f"file_{len(ids)}.txt",
                content="content",
            )
            assert proposal.proposal_id not in ids
            ids.add(proposal.proposal_id)

    def test_approval_binds_to_exact_proposal_hash(self):
        """Approval binds to exact proposal hash."""
        proposal = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="hash_test.txt",
            content="original",
        )
        self.cpm.submit_for_approval(proposal.proposal_id)
        
        # Tamper with proposal after submission
        proposal.content = "tampered"
        
        with pytest.raises(ValueError, match="Proposal integrity check failed"):
            self.cpm.approve(proposal.proposal_id)


class TestCreateTextFile:
    """Tests for CREATE_TEXT_FILE proposals."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.workspace = Path(self.temp_dir) / "workspace"
        self.workspace.mkdir(parents=True)
        (self.workspace / "existing.txt").write_text("existing")
        
        self.wm = WorkspaceManager()
        self.wm.select_workspace(str(self.workspace))
        self.cpm = ChangeProposalManager(self.wm)

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_new_text_file_creation(self):
        """Approved creation creates exactly the expected file with expected content."""
        proposal = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="new_file.txt",
            content="hello world",
        )
        self.cpm.submit_for_approval(proposal.proposal_id)
        self.cpm.approve(proposal.proposal_id)
        applied = self.cpm.apply(proposal.proposal_id)
        
        assert applied.state == "applied"
        target = Path(self.workspace) / "new_file.txt"
        assert target.exists()
        assert target.read_text() == "hello world"

    def test_rejected_creation_leaves_no_file(self):
        """Rejected creation leaves no file behind."""
        proposal = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="rejected.txt",
            content="rejected",
        )
        self.cpm.submit_for_approval(proposal.proposal_id)
        self.cpm.reject(proposal.proposal_id)
        
        target = Path(self.workspace) / "rejected.txt"
        assert not target.exists()

    def test_creation_outside_workspace_denied(self):
        """Creation outside active workspace is denied."""
        outside = Path(tempfile.mkdtemp()) / "outside.txt"
        
        proposal = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path=str(outside),
            content="outside",
        )
        
        # Should fail at creation or submission
        assert proposal.state in ("failed", "draft")
        assert proposal.error_code in ("invalid_path", "traversal", "no_workspace")

    def test_creation_with_traversal_attempt_denied(self):
        """Creation with traversal attempt is denied."""
        proposal = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="../outside.txt",
            content="traversal",
        )
        
        assert proposal.state == "failed"
        assert proposal.error_code in ("traversal", "invalid_path")

    def test_creation_to_sensitive_path_denied(self):
        """Creation to a sensitive path is denied per policy."""
        proposal = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path=".env",
            content="SECRET=123",
        )
        
        assert proposal.state == "failed"
        assert proposal.error_code == "sensitive_file"

    def test_existing_destination_causes_collision(self):
        """Existing destination causes collision/no-overwrite behavior."""
        proposal = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="existing.txt",
            content="new content",
        )
        
        assert proposal.state == "failed"
        assert proposal.error_code == "collision"

    def test_workspace_cleared_prevents_application(self):
        """Workspace cleared after proposal prevents application."""
        proposal = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="after_clear.txt",
            content="after clear",
        )
        self.cpm.submit_for_approval(proposal.proposal_id)
        self.cpm.approve(proposal.proposal_id)
        
        # Clear workspace
        self.cpm.workspace_manager.clear_workspace()
        
        applied = self.cpm.apply(proposal.proposal_id)
        assert applied.state == "failed"
        assert applied.error_code == "no_workspace"

    def test_expired_proposal_cannot_create(self):
        """Expired proposal cannot create a file."""
        proposal = self.cpm.create_proposal(
            operation="create_text_file",
            destination_path="expired.txt",
            content="expired",
            expires_in=0.001,
        )
        self.cpm.submit_for_approval(proposal.proposal_id)
        
        import time
        time.sleep(0.01)
        self.cpm.expire_stale_proposals()
        
        with pytest.raises(ValueError, match="not in approvable state"):
            self.cpm.approve(proposal.proposal_id)


class TestEditTextFile:
    """Tests for EDIT_TEXT_FILE proposals."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.workspace = Path(self.temp_dir) / "workspace"
        self.workspace.mkdir(parents=True)
        (self.workspace / "edit_me.txt").write_text("original content")
        (self.workspace / ".env").write_text("SECRET=123")
        (self.workspace / "binary.bin").write_bytes(b"\x00\x01\x02")
        
        self.wm = WorkspaceManager()
        self.wm.select_workspace(str(self.workspace))
        self.cpm = ChangeProposalManager(self.wm)

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_edit_proposal_does_not_modify_before_approval(self):
        """Edit proposal does not modify source before approval."""
        proposal = self.cpm.create_proposal(
            operation="edit_text_file",
            source_path="edit_me.txt",
            content="modified content",
        )
        
        # File should be unchanged
        target = Path(self.workspace) / "edit_me.txt"
        assert target.read_text() == "original content"

    def test_preview_includes_correct_diff(self):
        """Preview includes a correct diff."""
        proposal = self.cpm.create_proposal(
            operation="edit_text_file",
            source_path="edit_me.txt",
            content="modified content",
        )
        
        preview = proposal.preview
        assert preview is not None
        assert preview.diff_preview is not None
        assert "original content" in preview.diff_preview or "modified content" in preview.diff_preview
        assert preview.operation == "edit_text_file"

    def test_approved_edit_changes_file(self):
        """Approved edit changes exactly the intended file content."""
        proposal = self.cpm.create_proposal(
            operation="edit_text_file",
            source_path="edit_me.txt",
            content="new content here",
        )
        self.cpm.submit_for_approval(proposal.proposal_id)
        self.cpm.approve(proposal.proposal_id)
        applied = self.cpm.apply(proposal.proposal_id)
        
        assert applied.state == "applied"
        target = Path(self.workspace) / "edit_me.txt"
        assert target.read_text() == "new content here"

    def test_rejected_edit_leaves_original_unchanged(self):
        """Rejected edit leaves original file unchanged."""
        proposal = self.cpm.create_proposal(
            operation="edit_text_file",
            source_path="edit_me.txt",
            content="rejected change",
        )
        self.cpm.submit_for_approval(proposal.proposal_id)
        self.cpm.reject(proposal.proposal_id)
        
        target = Path(self.workspace) / "edit_me.txt"
        assert target.read_text() == "original content"

    def test_edit_outside_workspace_denied(self):
        """Edit outside workspace is denied."""
        outside = Path(tempfile.mkdtemp()) / "outside.txt"
        outside.write_text("outside")
        
        proposal = self.cpm.create_proposal(
            operation="edit_text_file",
            source_path=str(outside),
            content="outside edit",
        )
        
        assert proposal.state == "failed"
        assert proposal.error_code in ("not_found", "traversal", "no_workspace")

    def test_editing_sensitive_file_denied(self):
        """Editing a sensitive file is denied."""
        proposal = self.cpm.create_proposal(
            operation="edit_text_file",
            source_path=".env",
            content="NEW_SECRET=456",
        )
        
        assert proposal.state == "failed"
        assert proposal.error_code == "sensitive_file"

    def test_editing_binary_file_denied(self):
        """Editing a binary file is denied."""
        proposal = self.cpm.create_proposal(
            operation="edit_text_file",
            source_path="binary.bin",
            content="text",
        )
        
        assert proposal.state == "failed"
        assert proposal.error_code == "binary_file"

    def test_editing_stale_file_rejected(self):
        """Editing a file modified after proposal generation is rejected."""
        # Create proposal
        proposal = self.cpm.create_proposal(
            operation="edit_text_file",
            source_path="edit_me.txt",
            content="proposed edit",
        )
        self.cpm.submit_for_approval(proposal.proposal_id)
        self.cpm.approve(proposal.proposal_id)
        
        # Modify file externally
        target = Path(self.workspace) / "edit_me.txt"
        target.write_text("externally modified")
        
        # Apply should fail
        result = self.cpm.apply(proposal.proposal_id)
        assert result.state == "failed"
        assert result.error_code == "stale_source"


class TestMoveOrRename:
    """Tests for MOVE_OR_RENAME proposals."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.workspace = Path(self.temp_dir) / "workspace"
        self.workspace.mkdir(parents=True)
        (self.workspace / "move_me.txt").write_text("move me")
        (self.workspace / "subdir").mkdir()
        
        self.wm = WorkspaceManager()
        self.wm.select_workspace(str(self.workspace))
        self.cpm = ChangeProposalManager(self.wm)

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_rename_move_proposal_does_not_alter_before_approval(self):
        """Rename/move proposal does not alter paths before approval."""
        proposal = self.cpm.create_proposal(
            operation="move_or_rename",
            source_path="move_me.txt",
            destination_path="moved.txt",
        )
        
        # Source should still exist at original location
        source = Path(self.workspace) / "move_me.txt"
        dest = Path(self.workspace) / "moved.txt"
        assert source.exists()
        assert not dest.exists()

    def test_approved_rename_moves_file(self):
        """Approved rename moves exactly one file to expected destination."""
        proposal = self.cpm.create_proposal(
            operation="move_or_rename",
            source_path="move_me.txt",
            destination_path="renamed.txt",
        )
        self.cpm.submit_for_approval(proposal.proposal_id)
        self.cpm.approve(proposal.proposal_id)
        applied = self.cpm.apply(proposal.proposal_id)
        
        assert applied.state == "applied"
        assert not (Path(self.workspace) / "move_me.txt").exists()
        assert (Path(self.workspace) / "renamed.txt").exists()
        assert (Path(self.workspace) / "renamed.txt").read_text() == "move me"

    def test_rejected_rename_leaves_source_in_place(self):
        """Rejected rename leaves source in place and destination absent."""
        proposal = self.cpm.create_proposal(
            operation="move_or_rename",
            source_path="move_me.txt",
            destination_path="rejected_move.txt",
        )
        self.cpm.submit_for_approval(proposal.proposal_id)
        self.cpm.reject(proposal.proposal_id)
        
        assert (Path(self.workspace) / "move_me.txt").exists()
        assert not (Path(self.workspace) / "rejected_move.txt").exists()

    def test_destination_collision_denied(self):
        """Destination collision is denied/no-overwrite."""
        # Create destination file
        (self.workspace / "existing.txt").write_text("existing")
        
        proposal = self.cpm.create_proposal(
            operation="move_or_rename",
            source_path="move_me.txt",
            destination_path="existing.txt",
        )
        
        assert proposal.state == "failed"
        assert proposal.error_code == "collision_destination"

    def test_source_outside_workspace_denied(self):
        """Source outside workspace is denied."""
        outside = Path(tempfile.mkdtemp()) / "outside.txt"
        outside.write_text("outside")
        
        proposal = self.cpm.create_proposal(
            operation="move_or_rename",
            source_path=str(outside),
            destination_path="inside.txt",
        )
        
        assert proposal.state == "failed"
        assert proposal.error_code in ("not_found", "traversal", "no_workspace")

    def test_destination_outside_workspace_denied(self):
        """Destination outside workspace is denied."""
        outside = Path(tempfile.mkdtemp()) / "outside.txt"
        
        proposal = self.cpm.create_proposal(
            operation="move_or_rename",
            source_path="move_me.txt",
            destination_path=str(outside),
        )
        
        assert proposal.state == "failed"
        assert proposal.error_code in ("traversal", "invalid_path")

    def test_sensitive_source_handling_denied(self):
        """Sensitive source file handling denied."""
        (Path(self.temp_dir) / "workspace" / "secret.key").write_text("secret")
        self.wm.select_workspace(str(self.workspace))
        
        proposal = self.cpm.create_proposal(
            operation="move_or_rename",
            source_path="secret.key",
            destination_path="moved.key",
        )
        
        assert proposal.state == "failed"
        assert proposal.error_code == "sensitive_file"

    def test_moving_directory_recursively_denied(self):
        """Moving a directory recursively is denied in P2."""
        proposal = self.cpm.create_proposal(
            operation="move_or_rename",
            source_path="subdir",
            destination_path="moved_subdir",
        )
        
        # Directory is not a file - should fail
        assert proposal.state == "failed"
        assert proposal.error_code in ("not_file", "invalid_path", "not_found")

    def test_source_changed_after_proposal_blocks_application(self):
        """Source changed/removed after proposal blocks application."""
        proposal = self.cpm.create_proposal(
            operation="move_or_rename",
            source_path="move_me.txt",
            destination_path="moved.txt",
        )
        self.cpm.submit_for_approval(proposal.proposal_id)
        self.cpm.approve(proposal.proposal_id)
        
        # Remove source
        (Path(self.workspace) / "move_me.txt").unlink()
        
        result = self.cpm.apply(proposal.proposal_id)
        assert result.state == "failed"
        assert result.error_code in ("not_found", "stale_source")


class TestP1Regression:
    """Ensure P1 protections remain intact."""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.workspace = Path(self.temp_dir) / "workspace"
        self.workspace.mkdir(parents=True)
        (self.workspace / "test.txt").write_text("test")
        
        self.wm = WorkspaceManager()
        self.wm.select_workspace(str(self.workspace))
        self.cpm = ChangeProposalManager(self.wm)

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_p1_read_only_workspace_tests_continue_to_pass(self):
        """P1 read-only workspace tests continue to pass."""
        from workspace_manager import WorkspaceManager
        
        wm = WorkspaceManager()
        wm.select_workspace(str(self.workspace))
        
        # Read should work
        result = wm.read_file("test.txt")
        assert result.allowed
        
        # List should work
        result = wm.list_directory(".")
        assert result.allowed
        assert result.truncation.get("item_count", 0) > 0

    def test_p1_sensitive_file_policy_remains_enforced(self):
        """P1 sensitive-file policy remains enforced."""
        wm = WorkspaceManager()
        wm.select_workspace(str(self.workspace))
        (Path(self.workspace) / ".env").write_text("SECRET=123")
        
        result = wm.read_file(".env")
        assert not result.allowed
        assert result.denial_category == "sensitive_file"

    def test_p1_traversal_symlink_junction_protections_remain_used(self):
        """P1 traversal/symlink/junction protections remain used."""
        wm = WorkspaceManager()
        wm.select_workspace(str(self.workspace))
        
        # Traversal rejected
        result = wm.read_file("../outside.txt")
        assert not result.allowed
        assert result.denial_category == "traversal"

    def test_audit_records_contain_workspace_relative_paths(self):
        """Audit records contain workspace-relative paths and state transitions."""
        wm = WorkspaceManager()
        wm.select_workspace(str(self.workspace))
        
        wm.read_file("test.txt")
        records = wm.get_consulted_files()
        
        assert len(records) > 0
        assert not os.path.isabs(records[0].workspace_relative)
        assert records[0].allowed is True


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

    def teardown_method(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    @pytest.mark.skipif(os.name != "nt", reason="Windows junction test")
    def test_windows_junction_escape_rejected(self):
        """Windows junction pointing outside workspace is detected."""
        outside = Path(tempfile.mkdtemp()) / "outside"
        outside.mkdir()
        (outside / "secret.txt").write_text("secret")
        
        # Create junction
        link_path = Path(self.temp_dir) / "workspace" / "junction_to_outside"
        import os
        os.system(f'mklink /J "{link_path}" "{outside}"')
        
        wm = WorkspaceManager()
        wm.select_workspace(str(self.workspace))
        
        # Reading through junction should be denied
        result = wm.read_file("junction_to_outside/secret.txt")
        assert not result.allowed
        assert result.denial_category == "symlink_escape"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])