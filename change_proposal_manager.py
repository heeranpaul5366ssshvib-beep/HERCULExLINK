from __future__ import annotations
"""
============================================
HERCULE AI Operating System
Module: Change Proposal Manager (Stage P2)
Author: HERCULE Team
License: MIT
============================================

Change Proposal Manager for Safe Creation and Change Previews (Stage P2).

Provides:
- Proposal lifecycle management (create, approve, reject, cancel, apply, expire)
- Integration with P1 WorkspaceManager for path validation
- Audit trail integration
- Proposal persistence and retrieval
"""

import hashlib
import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from change_proposals import (
    ChangeProposal,
    ChangeOperation,
    ProposalState,
    ChangeErrorCode,
    ChangePreview,
    AutomationPlan,
    AutomationStep,
    AutomationState,
    AutomationStopPolicy,
    AutomationErrorCode,
)
from workspace_manager import WorkspaceManager, _matches_sensitive, _is_binary_file

try:
    from security.auditing.audit_manager import AuditManager
except Exception:
    AuditManager = None


# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------

DEFAULT_PROPOSAL_TIMEOUT = 300.0  # 5 minutes
DEFAULT_MAX_PREVIEW_LENGTH = 2000  # chars


# ----------------------------------------------------------------------
# Change Proposal Manager
# ----------------------------------------------------------------------


class ChangeProposalManager:
    """
    Manages the lifecycle of change proposals.
    
    Handles:
    - Proposal creation and validation
    - Approval/rejection/cancellation
    - Application of approved proposals
    - Expiration handling
    - Persistence and retrieval
    """
    
    def __init__(
        self,
        workspace_manager: WorkspaceManager,
        audit_manager: Optional[Any] = None,
        timeout_s: float = DEFAULT_PROPOSAL_TIMEOUT,
        max_preview_length: int = DEFAULT_MAX_PREVIEW_LENGTH,
    ):
        self.workspace_manager = workspace_manager
        self.audit = audit_manager
        self.timeout_s = float(timeout_s)
        self.max_preview_length = max_preview_length
        
        self._lock = threading.Lock()
        self._proposals: Dict[str, "ChangeProposal"] = {}
        self._proposals_by_workspace: Dict[str, List[str]] = {}  # workspace_root -> list of proposal_ids
    
    # ------------------------------------------------------------------
    # Proposal Creation
    # ------------------------------------------------------------------
    
    def create_proposal(
        self,
        operation: Union["ChangeOperation", str],
        source_path: Optional[str] = None,
        destination_path: Optional[str] = None,
        content: Optional[str] = None,
        workspace_root: Optional[str] = None,
        workspace_name: Optional[str] = None,
        actor: str = "system",
        expires_in: Optional[float] = None,
    ) -> "ChangeProposal":
        """
        Create a new change proposal in DRAFT state.
        
        Args:
            operation: Type of change (CREATE_TEXT_FILE, EDIT_TEXT_FILE, MOVE_OR_RENAME)
            source_path: Source file path (workspace-relative) - for edit/move/rename
            destination_path: Destination path (workspace-relative) - for create/move/rename
            content: File content for create/edit operations
            workspace_root: Override active workspace (defaults to active)
            workspace_name: Override workspace name
            actor: Actor creating the proposal
            expires_in: Seconds until proposal expires (defaults to manager timeout)
        
        Returns:
            Created ChangeProposal in DRAFT state
            
        Raises:
            ValueError: If required parameters missing or invalid
        """
        from change_proposals import ChangeProposal, ChangeOperation, ProposalState, ChangePreview, ChangeErrorCode
        
        # Convert string operation to enum if needed
        if isinstance(operation, str):
            operation = ChangeOperation(operation)
        
        # Use active workspace if not specified
        if workspace_root is None:
            if not self.workspace_manager.active_scope:
                raise ValueError("No active workspace selected")
            workspace_root = str(self.workspace_manager.active_scope.root)
            workspace_name = self.workspace_manager.active_scope.name
        else:
            workspace_name = workspace_name or Path(workspace_root).name
        
        # Generate proposal ID and timestamp
        proposal_id = uuid.uuid4().hex[:12]
        now = time.time()
        
        # Build base proposal
        proposal = ChangeProposal(
            proposal_id=proposal_id,
            operation=operation,
            state=ProposalState.DRAFT,
            workspace_root=workspace_root,
            workspace_name=workspace_name,
            source_path=source_path,
            destination_path=destination_path,
            content=content,
            created_at=now,
            expires_at=now + (expires_in if expires_in is not None else self.timeout_s),
            actor=actor,
        )
        
        # Validate and build proposal based on operation type
        if operation == ChangeOperation.CREATE_TEXT_FILE:
            proposal = self._build_create_proposal(proposal, destination_path, content)
        elif operation == ChangeOperation.EDIT_TEXT_FILE:
            proposal = self._build_edit_proposal(proposal, source_path, content)
        elif operation == ChangeOperation.MOVE_OR_RENAME:
            proposal = self._build_move_proposal(proposal, source_path, destination_path)
        else:
            raise ValueError(f"Unknown operation: {operation}")
        
        # Store proposal
        with self._lock:
            self._proposals[proposal.proposal_id] = proposal
            if workspace_root not in self._proposals_by_workspace:
                self._proposals_by_workspace[workspace_root] = []
            self._proposals_by_workspace[workspace_root].append(proposal.proposal_id)
        
        # Audit log
        if self.audit:
            self.audit.log(f"Proposal created: {proposal.proposal_id} ({operation.value})")
        
        return proposal
    
    def _build_create_proposal(
        self,
        proposal: "ChangeProposal",
        destination_path: str,
        content: Optional[str],
    ) -> "ChangeProposal":
        """Build CREATE_TEXT_FILE proposal with preview."""
        from change_proposals import ChangePreview, ChangeOperation, ProposalState, ChangeErrorCode
        from workspace_manager import _matches_sensitive, _is_binary_file
        
        proposal.operation = ChangeOperation.CREATE_TEXT_FILE
        proposal.destination_path = destination_path
        proposal.content = content
        # content_hash is computed in ChangeProposal.__post_init__
        
        # Validate destination
        resolved = self.workspace_manager._resolve_in_workspace(destination_path)
        if not resolved.allowed:
            proposal.state = ProposalState.FAILED
            proposal.error = resolved.reason
            proposal.error_code = ChangeErrorCode(resolved.denial_category)
            return proposal
        
        target_path = resolved.path
        proposal.destination_path = destination_path
        
        # Check for collision - P2: no overwrite by default
        exists = target_path.exists()
        if exists:
            if not target_path.is_file():
                proposal.state = ProposalState.FAILED
                proposal.error = "destination exists and is not a file"
                proposal.error_code = ChangeErrorCode.COLLISION_DESTINATION
                return proposal
            # File exists with different content - collision, no overwrite in P2
            try:
                existing_content = target_path.read_text(encoding="utf-8", errors="ignore")
                existing_hash = hashlib.sha256(existing_content.encode()).hexdigest()[:16]
                new_hash = hashlib.sha256(content.encode()).hexdigest()[:16] if content else None
                if new_hash == existing_hash:
                    # Same content - no-op
                    proposal.state = ProposalState.FAILED
                    proposal.error = "destination already exists with identical content"
                    proposal.error_code = ChangeErrorCode.NO_OP
                    return proposal
            except Exception:
                pass
            # Different content - collision
            proposal.state = ProposalState.FAILED
            proposal.error = "destination already exists (no overwrite in P2)"
            proposal.error_code = ChangeErrorCode.COLLISION
            return proposal
        
        # Check sensitive file policy
        sensitive = _matches_sensitive(Path(destination_path))
        if sensitive:
            proposal.state = ProposalState.FAILED
            proposal.error = f"sensitive file pattern: {sensitive}"
            proposal.error_code = ChangeErrorCode.SENSITIVE_FILE
            return proposal
        
        # Build preview
        preview = self._build_create_preview(destination_path, content, exists, False)
        proposal.preview = preview
        
        return proposal
    
    def _build_edit_proposal(
        self,
        proposal: "ChangeProposal",
        source_path: str,
        content: Optional[str],
    ) -> "ChangeProposal":
        """Build EDIT_TEXT_FILE proposal with diff preview."""
        from change_proposals import ChangePreview, ChangeOperation, ProposalState, ChangeErrorCode
        from workspace_manager import _matches_sensitive, _is_binary_file
        import difflib
        
        proposal.operation = ChangeOperation.EDIT_TEXT_FILE
        proposal.source_path = source_path
        proposal.content = content
        # content_hash is computed in ChangeProposal.__post_init__
        
        # Resolve and validate source
        resolved = self.workspace_manager._resolve_in_workspace(source_path)
        if not resolved.allowed:
            proposal.state = ProposalState.FAILED
            proposal.error = resolved.reason
            proposal.error_code = ChangeErrorCode(resolved.denial_category)
            return proposal
        
        target_path = resolved.path
        proposal.source_path = source_path
        
        if not target_path.exists() or not target_path.is_file():
            proposal.state = ProposalState.FAILED
            proposal.error = "source file not found"
            proposal.error_code = ChangeErrorCode.NOT_FOUND
            return proposal
        
        # Check sensitive file
        sensitive = _matches_sensitive(target_path)
        if sensitive:
            proposal.state = ProposalState.FAILED
            proposal.error = f"sensitive file pattern: {sensitive}"
            proposal.error_code = ChangeErrorCode.SENSITIVE_FILE
            return proposal
        
        # Check binary
        if _is_binary_file(target_path):
            proposal.state = ProposalState.FAILED
            proposal.error = "binary file not editable"
            proposal.error_code = ChangeErrorCode.BINARY_FILE
            return proposal
        
        # Read current content and compute hash
        try:
            current_content = target_path.read_text(encoding="utf-8", errors="ignore")
            proposal.source_hash = hashlib.sha256(current_content.encode()).hexdigest()[:16]
        except Exception as e:
            proposal.state = ProposalState.FAILED
            proposal.error = f"failed to read source: {e}"
            proposal.error_code = ChangeErrorCode.APPLICATION_FAILED
            return proposal
        
        # Check for no-op
        if content == current_content:
            proposal.state = ProposalState.FAILED
            proposal.error = "no change (content identical)"
            proposal.error_code = ChangeErrorCode.NO_OP
            return proposal
        
        # Generate diff preview
        diff = self._generate_diff(current_content, content, source_path)
        
        # Build preview
        preview = ChangePreview(
            operation=ChangeOperation.EDIT_TEXT_FILE,
            source_path=source_path,
            destination_path=source_path,
            content_preview=content[:200] + "..." if content and len(content) > 200 else content,
            diff_preview=diff[:500] + "..." if len(diff) > 500 else diff,
            exists=True,
            overwrite=True,
            warnings=[],
            source_hash=proposal.source_hash,
        )
        proposal.preview = preview
        
        return proposal
    
    def _build_move_proposal(
        self,
        proposal: "ChangeProposal",
        source_path: str,
        destination_path: str,
    ) -> "ChangeProposal":
        """Build MOVE_OR_RENAME proposal with collision detection."""
        from change_proposals import ChangePreview, ChangeOperation, ProposalState, ChangeErrorCode
        from workspace_manager import _matches_sensitive
        
        proposal.operation = ChangeOperation.MOVE_OR_RENAME
        proposal.source_path = source_path
        proposal.destination_path = destination_path
        
        # Resolve and validate source
        src_resolved = self.workspace_manager._resolve_in_workspace(source_path)
        if not src_resolved.allowed:
            proposal.state = ProposalState.FAILED
            proposal.error = src_resolved.reason
            proposal.error_code = ChangeErrorCode(src_resolved.denial_category)
            return proposal
        
        src_path = src_resolved.path
        proposal.source_path = source_path
        
        if not src_path.exists() or not src_path.is_file():
            proposal.state = ProposalState.FAILED
            proposal.error = "source file not found"
            proposal.error_code = ChangeErrorCode.NOT_FOUND
            return proposal
        
        # Check sensitive file
        sensitive = _matches_sensitive(src_path)
        if sensitive:
            proposal.state = ProposalState.FAILED
            proposal.error = f"sensitive file pattern: {sensitive}"
            proposal.error_code = ChangeErrorCode.SENSITIVE_FILE
            return proposal
        
        # Read source hash for stale detection
        try:
            src_content = src_path.read_text(encoding="utf-8", errors="ignore")
            proposal.source_hash = hashlib.sha256(src_content.encode()).hexdigest()[:16]
        except Exception as e:
            proposal.state = ProposalState.FAILED
            proposal.error = f"failed to read source: {e}"
            proposal.error_code = ChangeErrorCode.APPLICATION_FAILED
            return proposal
        
        # Resolve and validate destination
        dst_resolved = self.workspace_manager._resolve_in_workspace(destination_path)
        if not dst_resolved.allowed:
            proposal.state = ProposalState.FAILED
            proposal.error = dst_resolved.reason
            proposal.error_code = ChangeErrorCode(dst_resolved.denial_category)
            return proposal
        
        dst_path = dst_resolved.path
        proposal.destination_path = destination_path
        
        # Check destination collision - P2: no overwrite
        exists = dst_path.exists()
        if exists:
            proposal.state = ProposalState.FAILED
            proposal.error = "destination already exists"
            proposal.error_code = ChangeErrorCode.COLLISION_DESTINATION
            return proposal
        
        # Check if destination directory exists
        if not dst_path.parent.exists():
            proposal.state = ProposalState.FAILED
            proposal.error = "destination parent directory does not exist"
            proposal.error_code = ChangeErrorCode.INVALID_PATH
            return proposal
        
        # Check sensitive destination
        sensitive = _matches_sensitive(dst_path)
        if sensitive:
            proposal.state = ProposalState.FAILED
            proposal.error = f"sensitive destination pattern: {sensitive}"
            proposal.error_code = ChangeErrorCode.SENSITIVE_FILE
            return proposal
        
        # Build preview
        preview = ChangePreview(
            operation=ChangeOperation.MOVE_OR_RENAME,
            source_path=source_path,
            destination_path=destination_path,
            exists=False,
            overwrite=False,
            warnings=[],
            source_hash=proposal.source_hash,
        )
        proposal.preview = preview
        
        return proposal
    
    def _generate_diff(self, old_content: str, new_content: str, path: str) -> str:
        """Generate unified diff between old and new content."""
        import difflib
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        diff = difflib.unified_diff(old_lines, new_lines, fromfile=f"a/{path}", tofile=f"b/{path}", n=3)
        return "".join(diff)
    
    def _build_create_preview(
        self,
        destination_path: str,
        content: Optional[str],
        exists: bool,
        overwrite: bool,
    ) -> "ChangePreview":
        """Build preview for create operation."""
        from change_proposals import ChangePreview, ChangeOperation
        
        warnings = []
        if exists:
            warnings.append(f"Destination already exists, will be overwritten")
        
        # Truncate content for preview
        content_preview = None
        if content is not None:
            content_preview = content[:500] + ("..." if len(content) > 500 else "")
        
        truncation = None
        if content and len(content) > 2000:
            truncation = {"truncated": True, "reason": "preview_length", "message": f"Preview truncated to 500 chars"}
        
        return ChangePreview(
            operation=ChangeOperation.CREATE_TEXT_FILE,
            destination_path=destination_path,
            content_preview=content_preview,
            exists=exists,
            overwrite=overwrite,
            warnings=warnings,
            truncation=truncation,
        )
    
    # ------------------------------------------------------------------
    # Proposal Lifecycle Management
    # ------------------------------------------------------------------
    
    def submit_for_approval(self, proposal_id: str) -> "ChangeProposal":
        """Submit a DRAFT proposal for approval (PENDING_APPROVAL)."""
        from change_proposals import ProposalState
        
        with self._lock:
            proposal = self._proposals.get(proposal_id)
            if not proposal:
                raise ValueError(f"Proposal not found: {proposal_id}")
            
            if proposal.state != ProposalState.DRAFT:
                raise ValueError(f"Proposal not in DRAFT state: {proposal.state}")
            
            # Validate integrity
            if not proposal.verify_integrity():
                raise ValueError("Proposal integrity check failed")
            
            # Re-validate paths at submission time
            if proposal.operation == ChangeOperation.CREATE_TEXT_FILE:
                resolved = self.workspace_manager._resolve_in_workspace(proposal.destination_path)
                if not resolved.allowed:
                    proposal.state = ProposalState.FAILED
                    proposal.error = f"destination path no longer valid: {resolved.reason}"
                    proposal.error_code = ChangeErrorCode.INVALID_PATH
                    return proposal
            elif proposal.operation == ChangeOperation.EDIT_TEXT_FILE:
                resolved = self.workspace_manager._resolve_in_workspace(proposal.source_path)
                if not resolved.allowed:
                    proposal.state = ProposalState.FAILED
                    proposal.error = resolved.reason
                    proposal.error_code = ChangeErrorCode(resolved.denial_category)
                    return proposal
                # Check stale source
                target_path = Path(proposal.workspace_root) / proposal.source_path
                if target_path.exists():
                    current_content = target_path.read_text(encoding="utf-8", errors="ignore")
                    current_hash = hashlib.sha256(current_content.encode()).hexdigest()[:16]
                    if proposal.source_hash and current_hash != proposal.source_hash:
                        proposal.state = ProposalState.FAILED
                        proposal.error = "source file has changed since proposal creation"
                        proposal.error_code = ChangeErrorCode.STALE_SOURCE
                        return proposal
            elif proposal.operation == ChangeOperation.MOVE_OR_RENAME:
                src_resolved = self.workspace_manager._resolve_in_workspace(proposal.source_path)
                if not src_resolved.allowed:
                    proposal.state = ProposalState.FAILED
                    proposal.error = f"source path no longer valid: {src_resolved.reason}"
                    proposal.error_code = src_resolved.denial_category
                    return proposal
                
                dst_resolved = self.workspace_manager._resolve_in_workspace(proposal.destination_path)
                if not dst_resolved.allowed:
                    proposal.state = ProposalState.FAILED
                    proposal.error = f"destination path no longer valid: {dst_resolved.reason}"
                    proposal.error_code = dst_resolved.denial_category
                    return proposal
            
            # Re-validate paths
            # Re-check sensitive file policy
            if proposal.operation == ChangeOperation.CREATE_TEXT_FILE:
                sensitive = _matches_sensitive(Path(proposal.destination_path))
                if sensitive:
                    proposal.state = ProposalState.FAILED
                    proposal.error = f"sensitive file pattern: {sensitive}"
                    proposal.error_code = ChangeErrorCode.SENSITIVE_FILE
                    return proposal
            elif proposal.operation == ChangeOperation.EDIT_TEXT_FILE:
                sensitive = _matches_sensitive(Path(proposal.source_path))
                if sensitive:
                    proposal.state = ProposalState.FAILED
                    proposal.error = f"sensitive file pattern: {sensitive}"
                    proposal.error_code = ChangeErrorCode.SENSITIVE_FILE
                    return proposal
            
            proposal.state = ProposalState.PENDING_APPROVAL
            proposal.updated_at = time.time()
            
            # Audit
            if self.audit:
                self.audit.log(f"Proposal submitted for approval: {proposal.proposal_id} ({proposal.operation.value})")
            
            return proposal
    
    def approve(self, proposal_id: str, actor: str = "user") -> "ChangeProposal":
        """Approve a pending proposal."""
        from change_proposals import ProposalState
        
        with self._lock:
            proposal = self._proposals.get(proposal_id)
            if not proposal:
                raise ValueError(f"Proposal not found: {proposal_id}")
            
            if proposal.state != ProposalState.PENDING_APPROVAL:
                raise ValueError(f"Proposal not in approvable state: {proposal.state}")
            
            if not proposal.verify_integrity():
                raise ValueError("Proposal integrity check failed")
            
            proposal.state = ProposalState.APPROVED
            proposal.approved_at = time.time()
            proposal.approval_hash = proposal.proposal_hash
            proposal.updated_at = time.time()
            proposal.actor = actor
            
            # Audit
            if self.audit:
                self.audit.log(f"Proposal approved: {proposal.proposal_id} by {actor}")
            
            return proposal
    
    def reject(self, proposal_id: str, actor: str = "user", reason: str = "") -> "ChangeProposal":
        """Reject a pending proposal."""
        from change_proposals import ProposalState
        
        with self._lock:
            proposal = self._proposals.get(proposal_id)
            if not proposal:
                raise ValueError(f"Proposal not found: {proposal_id}")
            
            if proposal.state not in (ProposalState.DRAFT, ProposalState.PENDING_APPROVAL):
                raise ValueError(f"Proposal not in approvable state: {proposal.state}")
            
            proposal.state = ProposalState.REJECTED
            proposal.rejected_at = time.time()
            proposal.updated_at = time.time()
            proposal.actor = actor
            proposal.error = reason
            
            # Audit
            if self.audit:
                self.audit.log(f"Proposal rejected: {proposal.proposal_id} by {actor}: {reason}")
            
            return proposal
    
    def cancel(self, proposal_id: str, actor: str = "user") -> "ChangeProposal":
        """Cancel a draft or pending proposal."""
        from change_proposals import ProposalState
        
        with self._lock:
            proposal = self._proposals.get(proposal_id)
            if not proposal:
                raise ValueError(f"Proposal not found: {proposal_id}")
            
            if proposal.state not in (ProposalState.DRAFT, ProposalState.PENDING_APPROVAL):
                raise ValueError(f"Proposal not cancellable in state: {proposal.state}")
            
            proposal.state = ProposalState.CANCELLED
            proposal.updated_at = time.time()
            proposal.actor = actor
            
            # Audit
            if self.audit:
                self.audit.log(f"Proposal cancelled: {proposal.proposal_id} by {actor}")
            
            return proposal
    
    def apply(self, proposal_id: str) -> "ChangeProposal":
        """Apply an approved proposal to the filesystem."""
        from change_proposals import ProposalState, ChangeErrorCode
        import difflib
        
        with self._lock:
            proposal = self._proposals.get(proposal_id)
            if not proposal:
                raise ValueError(f"Proposal not found: {proposal_id}")
            
            if proposal.state != ProposalState.APPROVED:
                raise ValueError(f"Proposal not approved: {proposal.state}")
            
            if not proposal.verify_integrity():
                proposal.state = ProposalState.FAILED
                proposal.error = "Proposal integrity check failed"
                proposal.error_code = ChangeErrorCode.HASH_MISMATCH
                proposal.failed_at = time.time()
                proposal.updated_at = time.time()
                return proposal
            
            if proposal.approval_hash != proposal.proposal_hash:
                proposal.state = ProposalState.FAILED
                proposal.error = "Proposal modified after approval"
                proposal.error_code = ChangeErrorCode.PROPOSAL_HASH_MISMATCH
                proposal.failed_at = time.time()
                proposal.updated_at = time.time()
                return proposal
            
            # Check workspace still active
            if not self.workspace_manager.active_scope:
                proposal.state = ProposalState.FAILED
                proposal.error = "No active workspace"
                proposal.error_code = ChangeErrorCode.NO_WORKSPACE
                proposal.failed_at = time.time()
                proposal.updated_at = time.time()
                return proposal
            
            if self.workspace_manager.active_scope.root != Path(proposal.workspace_root):
                proposal.state = ProposalState.FAILED
                proposal.error = "Workspace changed since proposal creation"
                proposal.error_code = ChangeErrorCode.WORKSPACE_CHANGED
                proposal.failed_at = time.time()
                proposal.updated_at = time.time()
                return proposal
            
            if proposal.expires_at and time.time() > proposal.expires_at:
                proposal.state = ProposalState.EXPIRED
                proposal.error = "Proposal expired"
                proposal.error_code = ChangeErrorCode.STALE_PROPOSAL
                proposal.failed_at = time.time()
                proposal.updated_at = time.time()
                return proposal
            
            try:
                if proposal.operation == ChangeOperation.CREATE_TEXT_FILE:
                    self._apply_create(proposal)
                elif proposal.operation == ChangeOperation.EDIT_TEXT_FILE:
                    self._apply_edit(proposal)
                elif proposal.operation == ChangeOperation.MOVE_OR_RENAME:
                    self._apply_move(proposal)
                else:
                    raise ValueError(f"Unknown operation: {proposal.operation}")
                
                proposal.state = ProposalState.APPLIED
                proposal.applied_at = time.time()
                proposal.updated_at = time.time()
                
                # Compute result hash
                if proposal.operation == ChangeOperation.CREATE_TEXT_FILE:
                    target_path = Path(proposal.workspace_root) / proposal.destination_path
                elif proposal.operation == ChangeOperation.EDIT_TEXT_FILE:
                    target_path = Path(proposal.workspace_root) / proposal.source_path
                else:
                    target_path = Path(proposal.workspace_root) / proposal.destination_path
                
                if target_path.exists():
                    content = target_path.read_text(encoding="utf-8", errors="ignore")
                    proposal.result_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
                
                # Audit
                if self.audit:
                    self.audit.log(f"Proposal applied: {proposal.proposal_id} ({proposal.operation.value})")
                
                return proposal
            
            except RuntimeError as e:
                error_msg = str(e)
                if error_msg.startswith("STALE_SOURCE:"):
                    proposal.state = ProposalState.FAILED
                    proposal.error = error_msg
                    proposal.error_code = ChangeErrorCode.STALE_SOURCE
                    proposal.failed_at = time.time()
                    proposal.updated_at = time.time()
                    
                    if self.audit:
                        self.audit.log(f"Proposal application failed (stale source): {proposal.proposal_id}: {error_msg}")
                    
                    return proposal
                elif error_msg == "Source file no longer exists":
                    proposal.state = ProposalState.FAILED
                    proposal.error = error_msg
                    proposal.error_code = ChangeErrorCode.NOT_FOUND
                    proposal.failed_at = time.time()
                    proposal.updated_at = time.time()
                    
                    if self.audit:
                        self.audit.log(f"Proposal application failed (source not found): {proposal.proposal_id}: {error_msg}")
                    
                    return proposal
                elif error_msg == "Destination already exists":
                    proposal.state = ProposalState.FAILED
                    proposal.error = error_msg
                    proposal.error_code = ChangeErrorCode.COLLISION_DESTINATION
                    proposal.failed_at = time.time()
                    proposal.updated_at = time.time()
                    
                    if self.audit:
                        self.audit.log(f"Proposal application failed (collision): {proposal.proposal_id}: {error_msg}")
                    
                    return proposal
                else:
                    raise
            except Exception as e:
                proposal.state = ProposalState.FAILED
                proposal.error = str(e)
                proposal.error_code = ChangeErrorCode.APPLICATION_FAILED
                proposal.failed_at = time.time()
                proposal.updated_at = time.time()
                
                # Audit
                if self.audit:
                    self.audit.log(f"Proposal application failed: {proposal.proposal_id}: {e}")
                
                return proposal
    
    def _apply_create(self, proposal: "ChangeProposal") -> None:
        """Apply CREATE_TEXT_FILE proposal."""
        target_path = Path(proposal.workspace_root) / proposal.destination_path
        
        # Create parent directory if needed
        target_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write content
        content = proposal.content or ""
        target_path.write_text(content, encoding="utf-8")
    
    def _apply_edit(self, proposal: "ChangeProposal") -> None:
        """Apply EDIT_TEXT_FILE proposal with stale source check."""
        target_path = Path(proposal.workspace_root) / proposal.source_path
        
        # Verify source hasn't changed
        current_content = target_path.read_text(encoding="utf-8", errors="ignore")
        current_hash = hashlib.sha256(current_content.encode()).hexdigest()[:16]
        
        if proposal.source_hash and current_hash != proposal.source_hash:
            raise RuntimeError("STALE_SOURCE: Source file has changed since proposal creation")
        
        # Write new content
        content = proposal.content or ""
        target_path.write_text(content, encoding="utf-8")
    
    def _apply_move(self, proposal: "ChangeProposal") -> None:
        """Apply MOVE_OR_RENAME proposal."""
        src_path = Path(proposal.workspace_root) / proposal.source_path
        dst_path = Path(proposal.workspace_root) / proposal.destination_path
        
        # Verify source still exists and matches hash
        if not src_path.exists():
            raise RuntimeError("Source file no longer exists")
        
        current_content = src_path.read_text(encoding="utf-8", errors="ignore")
        current_hash = hashlib.sha256(current_content.encode()).hexdigest()[:16]
        
        if proposal.source_hash and current_hash != proposal.source_hash:
            raise RuntimeError("STALE_SOURCE: Source file has changed since proposal creation")
        
        # Verify destination doesn't exist
        if dst_path.exists():
            raise RuntimeError("Destination already exists")
        
        # Ensure parent directory exists
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Move file
        src_path.rename(dst_path)
    
    # ------------------------------------------------------------------
    # Expiration and Cleanup
    # ------------------------------------------------------------------
    
    def expire_stale_proposals(self) -> int:
        """Expire proposals past their expiration time. Returns count expired."""
        from change_proposals import ProposalState
        
        expired_count = 0
        now = time.time()
        
        with self._lock:
            for proposal in self._proposals.values():
                if proposal.state == ProposalState.PENDING_APPROVAL and proposal.expires_at and time.time() > proposal.expires_at:
                    proposal.state = ProposalState.EXPIRED
                    proposal.updated_at = time.time()
                    expired_count += 1
                    
                    if self.audit:
                        self.audit.log(f"Proposal expired: {proposal.proposal_id}")
        
        return expired_count
    
    def cleanup_expired(self, max_age_s: float = 3600.0) -> int:
        """Remove expired/cancelled/rejected proposals older than max_age_s."""
        removed = 0
        now = time.time()
        
        with self._lock:
            to_remove = []
            for proposal_id, proposal in self._proposals.items():
                if proposal.state in (ProposalState.REJECTED, ProposalState.CANCELLED, ProposalState.EXPIRED, ProposalState.APPLIED, ProposalState.FAILED):
                    if now - proposal.updated_at > max_age_s:
                        to_remove.append(proposal_id)
            
            for pid in to_remove:
                del self._proposals[pid]
                removed += 1
                
                # Clean up workspace index
                for ws_root, ids in self._proposals_by_workspace.items():
                    if pid in ids:
                        ids.remove(pid)
                        break
        
        return removed
    
    # ------------------------------------------------------------------
    # Query and Retrieval
    # ------------------------------------------------------------------
    
    def get_proposal(self, proposal_id: str) -> Optional["ChangeProposal"]:
        """Get a proposal by ID."""
        with self._lock:
            return self._proposals.get(proposal_id)
    
    def get_proposals_by_workspace(self, workspace_root: str) -> List["ChangeProposal"]:
        """Get all proposals for a workspace."""
        with self._lock:
            ids = self._proposals_by_workspace.get(workspace_root, [])
            return [self._proposals[pid] for pid in ids if pid in self._proposals]
    
    def get_pending_proposals(self, workspace_root: Optional[str] = None) -> List["ChangeProposal"]:
        """Get all pending approval proposals."""
        with self._lock:
            if workspace_root:
                ids = self._proposals_by_workspace.get(workspace_root, [])
                return [p for pid in ids if (p := self._proposals.get(pid)) and p.state == ProposalState.PENDING_APPROVAL]
            return [p for p in self._proposals.values() if p.state == ProposalState.PENDING_APPROVAL]
    
    def get_proposals_by_state(self, state: str, workspace_root: Optional[str] = None) -> List["ChangeProposal"]:
        """Get proposals by state."""
        from change_proposals import ProposalState
        state_enum = ProposalState(state) if isinstance(state, str) else state
        
        with self._lock:
            if workspace_root:
                ids = self._proposals_by_workspace.get(workspace_root, [])
                return [p for pid in ids if (p := self._proposals.get(pid)) and p.state == state_enum]
            return [p for p in self._proposals.values() if p.state == state_enum]
    
    def get_proposal_preview(self, proposal_id: str) -> Optional["ChangePreview"]:
        """Get preview for a proposal."""
        with self._lock:
            proposal = self._proposals.get(proposal_id)
            return proposal.preview if proposal else None
    
    def get_proposal_audit_trail(self, proposal_id: str) -> List[Dict[str, Any]]:
        """Get audit trail for a proposal."""
        proposal = self.get_proposal(proposal_id)
        if not proposal:
            return []
        
        trail = [
            {"event": "created", "timestamp": proposal.created_at},
        ]
        if proposal.approved_at:
            trail.append({"event": "approved", "timestamp": proposal.approved_at})
        if proposal.rejected_at:
            trail.append({"event": "rejected", "timestamp": proposal.rejected_at})
        if proposal.applied_at:
            trail.append({"event": "applied", "timestamp": proposal.applied_at})
        if proposal.failed_at:
            trail.append({"event": "failed", "timestamp": proposal.failed_at})
        if proposal.cancelled_at:
            trail.append({"event": "cancelled", "timestamp": proposal.cancelled_at})
        
        return trail
    
    # ------------------------------------------------------------------
    # Persistence (optional)
    # ------------------------------------------------------------------
    
    def save_proposals(self, path: str) -> None:
        """Save all proposals to JSON file."""
        with self._lock:
            data = {
                "proposals": [p.to_dict() for p in self._proposals.values()],
                "saved_at": time.time(),
            }
            Path(path).write_text(json.dumps(data, indent=2))
    
    def load_proposals(self, path: str) -> int:
        """Load proposals from JSON file. Returns count loaded."""
        with self._lock:
            data = json.loads(Path(path).read_text())
            count = 0
            for p_data in data.get("proposals", []):
                proposal = ChangeProposal.from_dict(p_data)
                self._proposals[proposal.proposal_id] = proposal
                if proposal.workspace_root not in self._proposals_by_workspace:
                    self._proposals_by_workspace[proposal.workspace_root] = []
                self._proposals_by_workspace[proposal.workspace_root].append(proposal.proposal_id)
                count += 1
            return count


# ----------------------------------------------------------------------
# Automation Plan Manager (Stage P3)
# ----------------------------------------------------------------------


class AutomationPlanManager:
    """
    Manages the lifecycle of automation plans.
    
    Handles:
    - Plan creation from multiple proposals
    - Plan validation and revalidation
    - Approval/rejection/cancellation
    - Execution with revalidation at each step
    - Verification of results
    - Expiration handling
    - Persistence and retrieval
    """
    
    def __init__(
        self,
        proposal_manager: "ChangeProposalManager",
        audit_manager: Optional[Any] = None,
        timeout_s: float = DEFAULT_PROPOSAL_TIMEOUT,
    ):
        self.proposal_manager = proposal_manager
        self.workspace_manager = proposal_manager.workspace_manager
        self.audit = audit_manager
        self.timeout_s = float(timeout_s)
        
        self._lock = threading.Lock()
        self._plans: Dict[str, "AutomationPlan"] = {}
        self._plans_by_workspace: Dict[str, List[str]] = {}
    
    # ------------------------------------------------------------------
    # Plan Creation
    # ------------------------------------------------------------------
    
    def create_plan(
        self,
        name: str,
        description: str = "",
        proposal_ids: Optional[List[str]] = None,
        workspace_root: Optional[str] = None,
        workspace_name: Optional[str] = None,
        stop_policy: Union["AutomationStopPolicy", str] = AutomationStopPolicy.STOP_ON_FAILURE,
        actor: str = "system",
        expires_in: Optional[float] = None,
    ) -> "AutomationPlan":
        """
        Create a new automation plan in DRAFT state.
        
        Args:
            name: Human-readable name for the plan
            description: Optional description
            proposal_ids: List of proposal IDs to include in the plan (must be in DRAFT or validated state)
            workspace_root: Override active workspace
            workspace_name: Override workspace name
            stop_policy: Failure handling policy
            actor: Actor creating the plan
            expires_in: Seconds until plan expires
        
        Returns:
            Created AutomationPlan in DRAFT state
        """
        from change_proposals import AutomationPlan, AutomationStep, AutomationState, AutomationStopPolicy, AutomationErrorCode
        
        # Convert string stop_policy to enum if needed
        if isinstance(stop_policy, str):
            stop_policy = AutomationStopPolicy(stop_policy)
        
        # Use active workspace if not specified
        if workspace_root is None:
            if not self.workspace_manager.active_scope:
                raise ValueError("No active workspace selected")
            workspace_root = str(self.workspace_manager.active_scope.root)
            workspace_name = self.workspace_manager.active_scope.name
        else:
            workspace_name = workspace_name or Path(workspace_root).name
        
        # Validate proposals if provided
        steps = []
        if proposal_ids:
            for i, proposal_id in enumerate(proposal_ids):
                proposal = self.proposal_manager.get_proposal(proposal_id)
                if not proposal:
                    # Allow missing proposals - validation will catch it
                    step_id = uuid.uuid4().hex[:8]
                    steps.append(AutomationStep(
                        step_id=step_id,
                        proposal_id=proposal_id,
                        order=i,
                        description=f"Step {i+1}: (missing proposal)",
                    ))
                    continue
                if proposal.workspace_root != workspace_root:
                    raise ValueError(f"Proposal {proposal_id} belongs to different workspace")
                # Allow any proposal state - validation will catch issues
                
                step_id = uuid.uuid4().hex[:8]
                steps.append(AutomationStep(
                    step_id=step_id,
                    proposal_id=proposal_id,
                    order=i,
                    description=f"Step {i+1}: {proposal.operation.value}",
                ))
        
        # Generate plan ID and timestamp
        plan_id = uuid.uuid4().hex[:12]
        now = time.time()
        
        # Build plan
        plan = AutomationPlan(
            plan_id=plan_id,
            name=name,
            description=description,
            state=AutomationState.DRAFT,
            workspace_root=workspace_root,
            workspace_name=workspace_name,
            steps=steps,
            stop_policy=stop_policy,
            created_at=now,
            expires_at=now + (expires_in if expires_in is not None else self.timeout_s),
            actor=actor,
        )
        
        # Store plan
        with self._lock:
            self._plans[plan.plan_id] = plan
            if workspace_root not in self._plans_by_workspace:
                self._plans_by_workspace[workspace_root] = []
            self._plans_by_workspace[workspace_root].append(plan.plan_id)
        
        # Audit log
        if self.audit:
            self.audit.log(f"Automation plan created: {plan.plan_id} ({name}) with {len(steps)} steps")
        
        return plan
    
    def add_step_to_plan(
        self,
        plan_id: str,
        proposal_id: str,
        description: str = "",
    ) -> "AutomationPlan":
        """Add a step to an existing DRAFT plan."""
        from change_proposals import AutomationStep, AutomationState, AutomationErrorCode
        
        with self._lock:
            plan = self._plans.get(plan_id)
            if not plan:
                raise ValueError(f"Plan not found: {plan_id}")
            
            if plan.state != AutomationState.DRAFT:
                raise ValueError(f"Plan not in DRAFT state: {plan.state}")
            
            proposal = self.proposal_manager.get_proposal(proposal_id)
            if not proposal:
                raise ValueError(f"Proposal not found: {proposal_id}")
            if proposal.workspace_root != plan.workspace_root:
                raise ValueError(f"Proposal belongs to different workspace")
            
            step_id = uuid.uuid4().hex[:8]
            new_order = len(plan.steps)
            step = AutomationStep(
                step_id=step_id,
                proposal_id=proposal_id,
                order=new_order,
                description=description or f"Step {new_order+1}: {proposal.operation.value}",
            )
            plan.steps.append(step)
            plan.updated_at = time.time()
            plan.plan_hash = plan._compute_hash()
            
            if self.audit:
                self.audit.log(f"Step added to plan {plan_id}: {step_id} ({proposal_id})")
            
            return plan
    
    # ------------------------------------------------------------------
    # Plan Validation
    # ------------------------------------------------------------------
    
    def validate_plan(self, plan_id: str) -> "AutomationPlan":
        """Validate all proposals in a plan and mark as VALIDATED."""
        from change_proposals import AutomationState, AutomationErrorCode
        
        with self._lock:
            plan = self._plans.get(plan_id)
            if not plan:
                raise ValueError(f"Plan not found: {plan_id}")
            
            if plan.state not in (AutomationState.DRAFT, AutomationState.VALIDATED):
                raise ValueError(f"Plan not in validatable state: {plan.state}")
            
            if not plan.steps:
                plan.state = AutomationState.FAILED
                plan.error = "Plan has no steps"
                plan.error_code = AutomationErrorCode.NO_PROPOSALS
                plan.updated_at = time.time()
                return plan
            
            # Validate each proposal
            for step in plan.steps:
                proposal = self.proposal_manager.get_proposal(step.proposal_id)
                if not proposal:
                    plan.state = AutomationState.FAILED
                    plan.error = f"Proposal not found: {step.proposal_id}"
                    plan.error_code = AutomationErrorCode.EXECUTION_FAILED
                    plan.updated_at = time.time()
                    return plan
                
                if not proposal.verify_integrity():
                    plan.state = AutomationState.FAILED
                    plan.error = f"Proposal integrity check failed: {step.proposal_id}"
                    plan.error_code = AutomationErrorCode.PROPOSAL_TAMPERED
                    plan.updated_at = time.time()
                    return plan
                
                # Check proposal state is valid for inclusion
                if proposal.state not in (ProposalState.DRAFT, ProposalState.PENDING_APPROVAL, ProposalState.APPROVED):
                    # If proposal failed, propagate its error code
                    if proposal.state == ProposalState.FAILED and proposal.error_code:
                        plan.state = AutomationState.FAILED
                        plan.error = f"Proposal {step.proposal_id} failed: {proposal.error}"
                        plan.error_code = proposal.error_code
                        plan.updated_at = time.time()
                        return plan
                    plan.state = AutomationState.FAILED
                    plan.error = f"Proposal not in valid state: {proposal.state}"
                    plan.error_code = AutomationErrorCode.INVALID_STATE
                    plan.updated_at = time.time()
                    return plan
            
            # All proposals valid
            plan.state = AutomationState.VALIDATED
            plan.updated_at = time.time()
            plan.plan_hash = plan._compute_hash()
            
            if self.audit:
                self.audit.log(f"Automation plan validated: {plan.plan_id}")
            
            return plan
    
    def submit_for_approval(self, plan_id: str) -> "AutomationPlan":
        """Submit a VALIDATED plan for approval (PENDING_APPROVAL)."""
        from change_proposals import AutomationState, AutomationErrorCode, ProposalState
        
        with self._lock:
            plan = self._plans.get(plan_id)
            if not plan:
                raise ValueError(f"Plan not found: {plan_id}")
            
            if plan.state != AutomationState.VALIDATED:
                raise ValueError(f"Plan not in VALIDATED state: {plan.state}")
            
            if not plan.verify_integrity():
                raise ValueError("Plan integrity check failed")
            
            # Re-validate all proposals at submission time
            for step in plan.steps:
                proposal = self.proposal_manager.get_proposal(step.proposal_id)
                if not proposal:
                    plan.state = AutomationState.FAILED
                    plan.error = f"Proposal not found: {step.proposal_id}"
                    plan.error_code = AutomationErrorCode.EXECUTION_FAILED
                    plan.updated_at = time.time()
                    return plan
                
                # Submit each proposal for approval if not already
                if proposal.state == ProposalState.DRAFT:
                    try:
                        self.proposal_manager.submit_for_approval(proposal.proposal_id)
                    except ValueError as e:
                        plan.state = AutomationState.FAILED
                        plan.error = f"Failed to submit proposal {step.proposal_id}: {e}"
                        plan.error_code = AutomationErrorCode.EXECUTION_FAILED
                        plan.updated_at = time.time()
                        return plan
            
            plan.state = AutomationState.PENDING_APPROVAL
            plan.updated_at = time.time()
            
            if self.audit:
                self.audit.log(f"Automation plan submitted for approval: {plan.plan_id}")
            
            return plan
    
    def approve(self, plan_id: str, actor: str = "user") -> "AutomationPlan":
        """Approve a pending automation plan."""
        from change_proposals import AutomationState, AutomationErrorCode
        
        with self._lock:
            plan = self._plans.get(plan_id)
            if not plan:
                raise ValueError(f"Plan not found: {plan_id}")
            
            if plan.state != AutomationState.PENDING_APPROVAL:
                raise ValueError(f"Plan not in approvable state: {plan.state}")
            
            if not plan.verify_integrity():
                raise ValueError("Plan integrity check failed")
            
            # Approve all proposals in the plan
            for step in plan.steps:
                proposal = self.proposal_manager.get_proposal(step.proposal_id)
                if proposal and proposal.state == ProposalState.PENDING_APPROVAL:
                    try:
                        self.proposal_manager.approve(proposal.proposal_id, actor)
                    except ValueError as e:
                        plan.state = AutomationState.FAILED
                        plan.error = f"Failed to approve proposal {step.proposal_id}: {e}"
                        plan.error_code = AutomationErrorCode.APPROVAL_INVALID
                        plan.updated_at = time.time()
                        return plan
            
            plan.state = AutomationState.APPROVED
            plan.approved_at = time.time()
            plan.approval_hash = plan.plan_hash
            plan.updated_at = time.time()
            plan.actor = actor
            
            if self.audit:
                self.audit.log(f"Automation plan approved: {plan.plan_id} by {actor}")
            
            return plan
    
    def reject(self, plan_id: str, actor: str = "user", reason: str = "") -> "AutomationPlan":
        """Reject a pending automation plan."""
        from change_proposals import AutomationState
        
        with self._lock:
            plan = self._plans.get(plan_id)
            if not plan:
                raise ValueError(f"Plan not found: {plan_id}")
            
            if plan.state not in (AutomationState.DRAFT, AutomationState.VALIDATED, AutomationState.PENDING_APPROVAL):
                raise ValueError(f"Plan not in rejectable state: {plan.state}")
            
            # Reject all proposals in the plan
            for step in plan.steps:
                proposal = self.proposal_manager.get_proposal(step.proposal_id)
                if proposal and proposal.state in (ProposalState.DRAFT, ProposalState.PENDING_APPROVAL):
                    try:
                        self.proposal_manager.reject(proposal.proposal_id, actor, reason)
                    except ValueError:
                        pass  # Ignore rejection failures
            
            plan.state = AutomationState.REJECTED
            plan.rejected_at = time.time()
            plan.updated_at = time.time()
            plan.actor = actor
            plan.error = reason
            
            if self.audit:
                self.audit.log(f"Automation plan rejected: {plan.plan_id} by {actor}: {reason}")
            
            return plan
    
    def cancel(self, plan_id: str, actor: str = "user") -> "AutomationPlan":
        """Cancel a draft or pending automation plan."""
        from change_proposals import AutomationState
        
        with self._lock:
            plan = self._plans.get(plan_id)
            if not plan:
                raise ValueError(f"Plan not found: {plan_id}")
            
            if plan.state not in (AutomationState.DRAFT, AutomationState.VALIDATED, AutomationState.PENDING_APPROVAL):
                raise ValueError(f"Plan not cancellable in state: {plan.state}")
            
            # Cancel all proposals in the plan
            for step in plan.steps:
                proposal = self.proposal_manager.get_proposal(step.proposal_id)
                if proposal and proposal.state in (ProposalState.DRAFT, ProposalState.PENDING_APPROVAL):
                    try:
                        self.proposal_manager.cancel(proposal.proposal_id, actor)
                    except ValueError:
                        pass
            
            plan.state = AutomationState.CANCELLED
            plan.cancelled_at = time.time()
            plan.updated_at = time.time()
            plan.actor = actor
            
            if self.audit:
                self.audit.log(f"Automation plan cancelled: {plan.plan_id} by {actor}")
            
            return plan
    
    # ------------------------------------------------------------------
    # Plan Execution
    # ------------------------------------------------------------------
    
    def execute_plan(self, plan_id: str, dry_run: bool = False) -> "AutomationPlan":
        """
        Execute an approved automation plan.
        
        Args:
            plan_id: ID of the plan to execute
            dry_run: If True, validate and simulate but don't apply changes
        
        Returns:
            Plan with updated state and execution results
        """
        from change_proposals import AutomationState, AutomationErrorCode, ProposalState
        
        with self._lock:
            plan = self._plans.get(plan_id)
            if not plan:
                raise ValueError(f"Plan not found: {plan_id}")
            
            if plan.state != AutomationState.APPROVED:
                raise ValueError(f"Plan not approved: {plan.state}")
            
            if not plan.verify_integrity():
                plan.state = AutomationState.FAILED
                plan.error = "Plan integrity check failed"
                plan.error_code = AutomationErrorCode.PLAN_TAMPERED
                plan.failed_at = time.time()
                plan.updated_at = time.time()
                return plan
            
            if plan.approval_hash != plan.plan_hash:
                plan.state = AutomationState.FAILED
                plan.error = "Plan modified after approval"
                plan.error_code = AutomationErrorCode.PLAN_TAMPERED
                plan.failed_at = time.time()
                plan.updated_at = time.time()
                return plan
            
            # Check workspace still active
            if not self.workspace_manager.active_scope:
                plan.state = AutomationState.FAILED
                plan.error = "No active workspace"
                plan.error_code = AutomationErrorCode.WORKSPACE_ESCAPE
                plan.failed_at = time.time()
                plan.updated_at = time.time()
                return plan
            
            if self.workspace_manager.active_scope.root != Path(plan.workspace_root):
                plan.state = AutomationState.FAILED
                plan.error = "Workspace changed since plan creation"
                plan.error_code = AutomationErrorCode.WORKSPACE_ESCAPE
                plan.failed_at = time.time()
                plan.updated_at = time.time()
                return plan
            
            if plan.expires_at and time.time() > plan.expires_at:
                plan.state = AutomationState.FAILED
                plan.error = "Plan expired"
                plan.error_code = AutomationErrorCode.APPROVAL_EXPIRED
                plan.failed_at = time.time()
                plan.updated_at = time.time()
                return plan
            
            plan.state = AutomationState.EXECUTING
            plan.executed_at = time.time()
            plan.updated_at = time.time()
            
            if self.audit:
                self.audit.log(f"Automation plan execution started: {plan.plan_id} (dry_run={dry_run})")
        
        # Execute each step
        results = []
        failed = False
        
        for step in plan.steps:
            proposal = self.proposal_manager.get_proposal(step.proposal_id)
            if not proposal:
                step.verified = False
                step.verification_error = "Proposal not found"
                failed = True
                results.append(f"Step {step.order} ({step.proposal_id}): PROPOSAL_NOT_FOUND")
                if plan.stop_policy == AutomationStopPolicy.STOP_ON_FAILURE:
                    break
                continue
            
            if dry_run:
                # Dry-run: just validate, don't apply
                try:
                    # Re-validate proposal
                    self._revalidate_proposal_before_execution(proposal)
                    step.verified = True
                    results.append(f"Step {step.order} ({step.proposal_id}): DRY_RUN_OK")
                except ValueError as e:
                    step.verified = False
                    step.verification_error = str(e)
                    failed = True
                    results.append(f"Step {step.order} ({step.proposal_id}): DRY_RUN_FAILED - {e}")
                    if plan.stop_policy == AutomationStopPolicy.STOP_ON_FAILURE:
                        break
                continue
            
            # Actual execution
            try:
                # Re-validate before execution
                self._revalidate_proposal_before_execution(proposal)
                
                # Apply the proposal
                applied_proposal = self.proposal_manager.apply(proposal.proposal_id)
                
                # Verify the result
                verification_result = self._verify_proposal_result(applied_proposal)
                step.verified = verification_result["verified"]
                step.verification_error = verification_result.get("error")
                step.result_hash = applied_proposal.result_hash
                
                if step.verified:
                    results.append(f"Step {step.order} ({step.proposal_id}): APPLIED_AND_VERIFIED")
                else:
                    failed = True
                    results.append(f"Step {step.order} ({step.proposal_id}): VERIFICATION_FAILED - {step.verification_error}")
                    if plan.stop_policy == AutomationStopPolicy.STOP_ON_FAILURE:
                        break
                        
            except ValueError as e:
                step.verified = False
                step.verification_error = str(e)
                failed = True
                results.append(f"Step {step.order} ({step.proposal_id}): EXECUTION_FAILED - {e}")
                if plan.stop_policy == AutomationStopPolicy.STOP_ON_FAILURE:
                    break
            except Exception as e:
                step.verified = False
                step.verification_error = f"Unexpected error: {e}"
                failed = True
                results.append(f"Step {step.order} ({step.proposal_id}): UNEXPECTED_ERROR - {e}")
                if plan.stop_policy == AutomationStopPolicy.STOP_ON_FAILURE:
                    break
        
        # Update plan state based on results
        with self._lock:
            plan = self._plans.get(plan_id)
            if not plan:
                raise ValueError(f"Plan not found: {plan_id}")
            
            plan.updated_at = time.time()
            plan.result_summary = "; ".join(results)
            
            if dry_run:
                plan.state = AutomationState.VERIFIED if not failed else AutomationState.FAILED
                if failed:
                    plan.error = "Dry-run validation failed"
                    plan.error_code = AutomationErrorCode.DRY_RUN_MODE
                    plan.failed_at = time.time()
                if self.audit:
                    self.audit.log(f"Automation plan dry-run completed: {plan.plan_id} (failed={failed})")
                return plan
            
            if failed:
                # Check if any steps succeeded
                any_succeeded = any(s.verified for s in plan.steps)
                if any_succeeded:
                    plan.state = AutomationState.PARTIALLY_APPLIED
                    plan.error = "Some steps failed during execution"
                    plan.error_code = AutomationErrorCode.PARTIALLY_APPLIED
                    plan.failed_at = time.time()
                else:
                    plan.state = AutomationState.FAILED
                    plan.error = "All steps failed during execution"
                    plan.error_code = AutomationErrorCode.EXECUTION_FAILED
                    plan.failed_at = time.time()
            else:
                plan.state = AutomationState.VERIFIED
                plan.error = None
                plan.error_code = None
            
            if self.audit:
                self.audit.log(f"Automation plan execution completed: {plan.plan_id} (state={plan.state.value})")
            
            return plan
    
    def _revalidate_proposal_before_execution(self, proposal: "ChangeProposal") -> None:
        """Re-validate a proposal immediately before execution."""
        from change_proposals import ChangeErrorCode, ProposalState
        
        # Check proposal integrity
        if not proposal.verify_integrity():
            raise ValueError("Proposal integrity check failed")
        
        # Check approval binding
        if proposal.approval_hash != proposal.proposal_hash:
            raise ValueError("Proposal modified after approval")
        
        # Check workspace still active
        if not self.workspace_manager.active_scope:
            raise ValueError("No active workspace")
        
        if self.workspace_manager.active_scope.root != Path(proposal.workspace_root):
            raise ValueError("Workspace changed since proposal creation")
        
        # Check expiration
        if proposal.expires_at and time.time() > proposal.expires_at:
            raise ValueError("Proposal expired")
        
        # Re-validate paths and sensitive file policy
        if proposal.operation == ChangeOperation.CREATE_TEXT_FILE:
            resolved = self.workspace_manager._resolve_in_workspace(proposal.destination_path)
            if not resolved.allowed:
                raise ValueError(f"Destination path no longer valid: {resolved.reason}")
            sensitive = _matches_sensitive(Path(proposal.destination_path))
            if sensitive:
                raise ValueError(f"Sensitive file pattern: {sensitive}")
        elif proposal.operation == ChangeOperation.EDIT_TEXT_FILE:
            resolved = self.workspace_manager._resolve_in_workspace(proposal.source_path)
            if not resolved.allowed:
                raise ValueError(f"Source path no longer valid: {resolved.reason}")
            sensitive = _matches_sensitive(Path(proposal.source_path))
            if sensitive:
                raise ValueError(f"Sensitive file pattern: {sensitive}")
            # Check stale source
            target_path = Path(proposal.workspace_root) / proposal.source_path
            if target_path.exists():
                current_content = target_path.read_text(encoding="utf-8", errors="ignore")
                current_hash = hashlib.sha256(current_content.encode()).hexdigest()[:16]
                if proposal.source_hash and current_hash != proposal.source_hash:
                    raise ValueError("STALE_SOURCE: Source file has changed since proposal creation")
        elif proposal.operation == ChangeOperation.MOVE_OR_RENAME:
            src_resolved = self.workspace_manager._resolve_in_workspace(proposal.source_path)
            if not src_resolved.allowed:
                raise ValueError(f"Source path no longer valid: {src_resolved.reason}")
            dst_resolved = self.workspace_manager._resolve_in_workspace(proposal.destination_path)
            if not dst_resolved.allowed:
                raise ValueError(f"Destination path no longer valid: {dst_resolved.reason}")
            # Check stale source
            src_path = Path(proposal.workspace_root) / proposal.source_path
            if src_path.exists():
                current_content = src_path.read_text(encoding="utf-8", errors="ignore")
                current_hash = hashlib.sha256(current_content.encode()).hexdigest()[:16]
                if proposal.source_hash and current_hash != proposal.source_hash:
                    raise ValueError("STALE_SOURCE: Source file has changed since proposal creation")
            # Check destination collision
            dst_path = Path(proposal.workspace_root) / proposal.destination_path
            if dst_path.exists():
                raise ValueError("Destination already exists")
    
    def _verify_proposal_result(self, proposal: "ChangeProposal") -> Dict[str, Any]:
        """Verify that a proposal's application produced the expected result."""
        from change_proposals import ProposalState
        
        if proposal.state != ProposalState.APPLIED:
            return {"verified": False, "error": f"Proposal not applied: {proposal.state.value}"}
        
        try:
            if proposal.operation == ChangeOperation.CREATE_TEXT_FILE:
                target_path = Path(proposal.workspace_root) / proposal.destination_path
                if not target_path.exists():
                    return {"verified": False, "error": "Created file does not exist"}
                content = target_path.read_text(encoding="utf-8", errors="ignore")
                if proposal.content is not None and content != proposal.content:
                    return {"verified": False, "error": "Created file content does not match expected"}
                if proposal.content_hash:
                    actual_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
                    if actual_hash != proposal.content_hash:
                        return {"verified": False, "error": "Created file hash mismatch"}
                        
            elif proposal.operation == ChangeOperation.EDIT_TEXT_FILE:
                target_path = Path(proposal.workspace_root) / proposal.source_path
                if not target_path.exists():
                    return {"verified": False, "error": "Edited file does not exist"}
                content = target_path.read_text(encoding="utf-8", errors="ignore")
                if proposal.content is not None and content != proposal.content:
                    return {"verified": False, "error": "Edited file content does not match expected"}
                if proposal.content_hash:
                    actual_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
                    if actual_hash != proposal.content_hash:
                        return {"verified": False, "error": "Edited file hash mismatch"}
                        
            elif proposal.operation == ChangeOperation.MOVE_OR_RENAME:
                src_path = Path(proposal.workspace_root) / proposal.source_path
                dst_path = Path(proposal.workspace_root) / proposal.destination_path
                if src_path.exists():
                    return {"verified": False, "error": "Source file still exists after move"}
                if not dst_path.exists():
                    return {"verified": False, "error": "Destination file does not exist after move"}
                content = dst_path.read_text(encoding="utf-8", errors="ignore")
                if proposal.source_hash:
                    actual_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
                    if actual_hash != proposal.source_hash:
                        return {"verified": False, "error": "Moved file content hash mismatch"}
            
            return {"verified": True}
            
        except Exception as e:
            return {"verified": False, "error": f"Verification error: {e}"}
    
    # ------------------------------------------------------------------
    # Expiration and Cleanup
    # ------------------------------------------------------------------
    
    def expire_stale_plans(self) -> int:
        """Expire plans past their expiration time. Returns count expired."""
        from change_proposals import AutomationState
        
        expired_count = 0
        now = time.time()
        
        with self._lock:
            for plan in self._plans.values():
                if plan.state in (AutomationState.DRAFT, AutomationState.VALIDATED, AutomationState.PENDING_APPROVAL) and plan.expires_at and time.time() > plan.expires_at:
                    plan.state = AutomationState.EXPIRED
                    plan.updated_at = time.time()
                    expired_count += 1
                    
                    if self.audit:
                        self.audit.log(f"Automation plan expired: {plan.plan_id}")
        
        return expired_count
    
    def cleanup_old_plans(self, max_age_s: float = 3600.0) -> int:
        """Remove old plans in terminal states."""
        removed = 0
        now = time.time()
        
        with self._lock:
            to_remove = []
            for plan_id, plan in self._plans.items():
                if plan.state in (AutomationState.REJECTED, AutomationState.CANCELLED, AutomationState.EXPIRED, AutomationState.VERIFIED, AutomationState.FAILED, AutomationState.PARTIALLY_APPLIED):
                    if now - plan.updated_at > max_age_s:
                        to_remove.append(plan_id)
            
            for pid in to_remove:
                del self._plans[pid]
                removed += 1
                
                for ws_root, ids in self._plans_by_workspace.items():
                    if pid in ids:
                        ids.remove(pid)
                        break
        
        return removed
    
    # ------------------------------------------------------------------
    # Query and Retrieval
    # ------------------------------------------------------------------
    
    def get_plan(self, plan_id: str) -> Optional["AutomationPlan"]:
        """Get a plan by ID."""
        with self._lock:
            return self._plans.get(plan_id)
    
    def get_plans_by_workspace(self, workspace_root: str) -> List["AutomationPlan"]:
        """Get all plans for a workspace."""
        with self._lock:
            ids = self._plans_by_workspace.get(workspace_root, [])
            return [self._plans[pid] for pid in ids if pid in self._plans]
    
    def get_pending_plans(self, workspace_root: Optional[str] = None) -> List["AutomationPlan"]:
        """Get all pending approval plans."""
        from change_proposals import AutomationState
        with self._lock:
            if workspace_root:
                ids = self._plans_by_workspace.get(workspace_root, [])
                return [p for pid in ids if (p := self._plans.get(pid)) and p.state == AutomationState.PENDING_APPROVAL]
            return [p for p in self._plans.values() if p.state == AutomationState.PENDING_APPROVAL]
    
    def get_plans_by_state(self, state: str, workspace_root: Optional[str] = None) -> List["AutomationPlan"]:
        """Get plans by state."""
        from change_proposals import AutomationState
        state_enum = AutomationState(state) if isinstance(state, str) else state
        
        with self._lock:
            if workspace_root:
                ids = self._plans_by_workspace.get(workspace_root, [])
                return [p for pid in ids if (p := self._plans.get(pid)) and p.state == state_enum]
            return [p for p in self._plans.values() if p.state == state_enum]
    
    def get_plan_audit_trail(self, plan_id: str) -> List[Dict[str, Any]]:
        """Get audit trail for a plan."""
        plan = self.get_plan(plan_id)
        if not plan:
            return []
        
        trail = [
            {"event": "created", "timestamp": plan.created_at},
        ]
        if plan.approved_at:
            trail.append({"event": "approved", "timestamp": plan.approved_at})
        if plan.rejected_at:
            trail.append({"event": "rejected", "timestamp": plan.rejected_at})
        if plan.executed_at:
            trail.append({"event": "executed", "timestamp": plan.executed_at})
        if plan.failed_at:
            trail.append({"event": "failed", "timestamp": plan.failed_at})
        if plan.cancelled_at:
            trail.append({"event": "cancelled", "timestamp": plan.cancelled_at})
        
        return trail
    
    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    
    def save_plans(self, path: str) -> None:
        """Save all plans to JSON file."""
        with self._lock:
            data = {
                "plans": [p.to_dict() for p in self._plans.values()],
                "saved_at": time.time(),
            }
            Path(path).write_text(json.dumps(data, indent=2))
    
    def load_plans(self, path: str) -> int:
        """Load plans from JSON file. Returns count loaded."""
        with self._lock:
            data = json.loads(Path(path).read_text())
            count = 0
            for p_data in data.get("plans", []):
                plan = AutomationPlan.from_dict(p_data)
                self._plans[plan.plan_id] = plan
                if plan.workspace_root not in self._plans_by_workspace:
                    self._plans_by_workspace[plan.workspace_root] = []
                self._plans_by_workspace[plan.workspace_root].append(plan.plan_id)
                count += 1
            return count