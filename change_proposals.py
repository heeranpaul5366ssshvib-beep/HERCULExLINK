from __future__ import annotations
"""
============================================
HERCULE AI Operating System
Module: Change Proposals (Stage P2)
Author: HERCULE Team
License: MIT
============================================

Change Proposals for Safe Creation and Change Previews (Stage P2).

Provides:
- Structured change proposals for text file operations
- State machine: DRAFT -> PENDING_APPROVAL -> APPROVED/REJECTED/EXPIRED/CANCELLED -> APPLIED/FAILED
- Proposal lifecycle management with validation and revalidation
- Integration with P1 WorkspaceManager for path validation
- Audit trail integration
- Preview generation with diff support
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


# ----------------------------------------------------------------------
# Enums and Constants
# ----------------------------------------------------------------------


class ChangeOperation(str, Enum):
    """Type of change operation."""
    CREATE_TEXT_FILE = "create_text_file"
    EDIT_TEXT_FILE = "edit_text_file"
    MOVE_OR_RENAME = "move_or_rename"


class ProposalState(str, Enum):
    """Proposal lifecycle state."""
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    APPLIED = "applied"
    FAILED = "failed"


class ChangeErrorCode(str, Enum):
    """Structured error codes for change operations."""
    NO_WORKSPACE = "no_workspace"
    INVALID_PATH = "invalid_path"
    TRAVERSAL = "traversal"
    SENSITIVE_FILE = "sensitive_file"
    BINARY_FILE = "binary_file"
    SIZE_LIMIT = "size_limit"
    COLLISION = "collision"
    NO_OP = "no_op"
    STALE_SOURCE = "stale_source"
    COLLISION_DESTINATION = "collision_destination"
    STALE_PROPOSAL = "stale_proposal"
    HASH_MISMATCH = "hash_mismatch"
    INVALID_STATE = "invalid_state"
    NOT_FOUND = "not_found"
    PERMISSION_DENIED = "permission_denied"
    APPLICATION_FAILED = "application_failed"
    WORKSPACE_CHANGED = "workspace_changed"
    PROPOSAL_HASH_MISMATCH = "proposal_hash_mismatch"
    SYMLINK_ESCAPE = "symlink_escape"


class AutomationState(str, Enum):
    """Automation plan lifecycle state."""
    DRAFT = "draft"
    VALIDATED = "validated"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    EXECUTING = "executing"
    VERIFIED = "verified"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    FAILED = "failed"
    PARTIALLY_APPLIED = "partially_applied"


class AutomationStopPolicy(str, Enum):
    """Policy for handling failures during automation execution."""
    STOP_ON_FAILURE = "stop_on_failure"
    CONTINUE_INDEPENDENT_STEPS = "continue_independent_steps"


class AutomationErrorCode(str, Enum):
    """Structured error codes for automation operations."""
    APPROVAL_REQUIRED = "approval_required"
    APPROVAL_EXPIRED = "approval_expired"
    APPROVAL_INVALID = "approval_invalid"
    PROPOSAL_TAMPERED = "proposal_tampered"
    PLAN_TAMPERED = "plan_tampered"
    STALE_SOURCE = "stale_source"
    DESTINATION_COLLISION = "destination_collision"
    PATH_POLICY_DENIED = "path_policy_denied"
    SENSITIVE_TARGET_DENIED = "sensitive_target_denied"
    WORKSPACE_ESCAPE = "workspace_escape"
    EXECUTION_FAILED = "execution_failed"
    VERIFICATION_FAILED = "verification_failed"
    PARTIALLY_APPLIED = "partially_applied"
    ALREADY_APPLIED = "already_applied"
    INVALID_STOP_POLICY = "invalid_stop_policy"
    NO_PROPOSALS = "no_proposals"
    PLAN_NOT_APPROVED = "plan_not_approved"
    DRY_RUN_MODE = "dry_run_mode"
    INVALID_STATE = "invalid_state"


# ----------------------------------------------------------------------
# Data Classes
# ----------------------------------------------------------------------


@dataclass
class ChangePreview:
    """User-reviewable preview of a proposed change."""
    operation: "ChangeOperation"
    source_path: Optional[str] = None
    destination_path: Optional[str] = None
    content_preview: Optional[str] = None
    diff_preview: Optional[str] = None
    exists: bool = False
    overwrite: bool = False
    warnings: List[str] = field(default_factory=list)
    truncation: Optional[Dict[str, Any]] = None
    source_hash: Optional[str] = None
    destination_hash: Optional[str] = None


@dataclass
class AutomationStep:
    """A single step in an automation plan, referencing a change proposal."""
    step_id: str
    proposal_id: str
    order: int
    description: str = ""
    # Verification result after execution
    verified: bool = False
    verification_error: Optional[str] = None
    result_hash: Optional[str] = None


@dataclass
class AutomationPlan:
    """An approved automation plan containing multiple change proposals."""
    plan_id: str
    name: str
    description: str = ""
    state: "AutomationState" = AutomationState.DRAFT
    
    # Workspace binding
    workspace_root: str = ""
    workspace_name: str = ""
    
    # Steps (ordered list of proposal references)
    steps: List["AutomationStep"] = field(default_factory=list)
    
    # Stop policy for failure handling
    stop_policy: "AutomationStopPolicy" = AutomationStopPolicy.STOP_ON_FAILURE
    
    # Plan metadata
    plan_hash: str = ""
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    updated_at: float = field(default_factory=time.time)
    
    # Approval tracking
    approved_at: Optional[float] = None
    rejected_at: Optional[float] = None
    executed_at: Optional[float] = None
    failed_at: Optional[float] = None
    approval_hash: Optional[str] = None  # Hash of plan at approval time
    
    # Cancellation tracking
    cancelled_at: Optional[float] = None
    
    # Cancellation tracking
    cancelled_at: Optional[float] = None
    
    # Execution result
    result_summary: Optional[str] = None
    error: Optional[str] = None
    error_code: Optional["AutomationErrorCode"] = None
    
    # Actor/source
    actor: str = "system"
    
    # Audit references
    audit_refs: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        # Ensure enums are proper types
        if isinstance(self.state, str):
            self.state = AutomationState(self.state)
        if isinstance(self.stop_policy, str):
            self.stop_policy = AutomationStopPolicy(self.stop_policy)
        if self.error_code and isinstance(self.error_code, str):
            self.error_code = AutomationErrorCode(self.error_code)
        
        if not self.plan_hash:
            self.plan_hash = self._compute_hash()
    
    def _compute_hash(self) -> str:
        """Compute deterministic hash of plan content for integrity verification."""
        data = {
            "name": self.name,
            "workspace_root": self.workspace_root,
            "stop_policy": self.stop_policy.value,
            "steps": [
                {
                    "step_id": s.step_id,
                    "proposal_id": s.proposal_id,
                    "order": s.order,
                    "description": s.description,
                }
                for s in self.steps
            ],
        }
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]
    
    def verify_integrity(self) -> bool:
        """Verify plan hasn't been tampered with since creation."""
        return self._compute_hash() == self.plan_hash
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize plan for storage/transmission."""
        return {
            "plan_id": self.plan_id,
            "name": self.name,
            "description": self.description,
            "state": self.state.value,
            "workspace_root": self.workspace_root,
            "workspace_name": self.workspace_name,
            "steps": [
                {
                    "step_id": s.step_id,
                    "proposal_id": s.proposal_id,
                    "order": s.order,
                    "description": s.description,
                    "verified": s.verified,
                    "verification_error": s.verification_error,
                    "result_hash": s.result_hash,
                }
                for s in self.steps
            ],
            "stop_policy": self.stop_policy.value,
            "plan_hash": self.plan_hash,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "updated_at": self.updated_at,
            "approved_at": self.approved_at,
            "rejected_at": self.rejected_at,
            "executed_at": self.executed_at,
            "failed_at": self.failed_at,
            "cancelled_at": self.cancelled_at,
            "approval_hash": self.approval_hash,
            "result_summary": self.result_summary,
            "error": self.error,
            "error_code": self.error_code.value if self.error_code else None,
            "actor": self.actor,
            "audit_refs": self.audit_refs,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AutomationPlan":
        """Deserialize plan from dictionary."""
        steps = []
        for s_data in data.get("steps", []):
            steps.append(AutomationStep(
                step_id=s_data["step_id"],
                proposal_id=s_data["proposal_id"],
                order=s_data["order"],
                description=s_data.get("description", ""),
                verified=s_data.get("verified", False),
                verification_error=s_data.get("verification_error"),
                result_hash=s_data.get("result_hash"),
            ))
        
        plan = cls(
            plan_id=data["plan_id"],
            name=data["name"],
            description=data.get("description", ""),
            state=AutomationState(data["state"]),
            workspace_root=data["workspace_root"],
            workspace_name=data["workspace_name"],
            steps=steps,
            stop_policy=AutomationStopPolicy(data["stop_policy"]),
            plan_hash=data["plan_hash"],
            created_at=data["created_at"],
            expires_at=data.get("expires_at"),
            updated_at=data["updated_at"],
            approved_at=data.get("approved_at"),
            rejected_at=data.get("rejected_at"),
            executed_at=data.get("executed_at"),
            failed_at=data.get("failed_at"),
            cancelled_at=data.get("cancelled_at"),
            approval_hash=data.get("approval_hash"),
            result_summary=data.get("result_summary"),
            error=data.get("error"),
            error_code=AutomationErrorCode(data["error_code"]) if data.get("error_code") else None,
            actor=data.get("actor", "system"),
            audit_refs=data.get("audit_refs", []),
        )
        return plan


@dataclass
class ChangeProposal:
    """A proposed filesystem change awaiting approval."""
    proposal_id: str
    operation: "ChangeOperation"
    state: "ProposalState" = ProposalState.DRAFT
    
    # Workspace binding
    workspace_root: str = ""
    workspace_name: str = ""
    
    # Paths (workspace-relative for portability)
    source_path: Optional[str] = None
    destination_path: Optional[str] = None
    
    # Content for create/edit operations
    content: Optional[str] = None
    content_hash: Optional[str] = None
    
    # For edit/move/rename: detect if source changed after proposal
    source_hash: Optional[str] = None
    
    # Proposal metadata
    proposal_hash: str = ""
    preview: Optional["ChangePreview"] = None
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    updated_at: float = field(default_factory=time.time)
    
    # Approval tracking
    approved_at: Optional[float] = None
    rejected_at: Optional[float] = None
    applied_at: Optional[float] = None
    failed_at: Optional[float] = None
    approval_hash: Optional[str] = None  # Hash of proposal at approval time
    
    # Application result
    result_hash: Optional[str] = None
    error: Optional[str] = None
    error_code: Optional["ChangeErrorCode"] = None
    
    # Actor/source
    actor: str = "system"
    
    # Audit references
    audit_refs: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        # Ensure operation, state, and error_code are enums BEFORE computing hash
        if isinstance(self.operation, str):
            self.operation = ChangeOperation(self.operation)
        if isinstance(self.state, str):
            self.state = ProposalState(self.state)
        if self.error_code and isinstance(self.error_code, str):
            self.error_code = ChangeErrorCode(self.error_code)
        
        # Compute content_hash from content if not provided
        if self.content is not None and self.content_hash is None:
            self.content_hash = hashlib.sha256(self.content.encode()).hexdigest()[:16]
        
        if not self.proposal_hash:
            self.proposal_hash = self._compute_hash()
    
    def _compute_hash(self) -> str:
        """Compute deterministic hash of proposal content for integrity verification."""
        data = {
            "operation": self.operation.value,
            "source_path": self.source_path,
            "destination_path": self.destination_path,
            "content_hash": self.content_hash,
            "content": self.content,
        }
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]
    
    def verify_integrity(self) -> bool:
        """Verify proposal hasn't been tampered with since creation."""
        # Check structural integrity
        if self._compute_hash() != self.proposal_hash:
            return False
        # Check content integrity: content_hash must match content if both present
        if self.content is not None and self.content_hash is not None:
            expected_hash = hashlib.sha256(self.content.encode()).hexdigest()[:16]
            if expected_hash != self.content_hash:
                return False
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize proposal for storage/transmission."""
        return {
            "proposal_id": self.proposal_id,
            "operation": self.operation.value,
            "state": self.state.value,
            "workspace_root": self.workspace_root,
            "workspace_name": self.workspace_name,
            "source_path": self.source_path,
            "destination_path": self.destination_path,
            "content": self.content,
            "content_hash": self.content_hash,
            "source_hash": self.source_hash,
            "proposal_hash": self.proposal_hash,
            "preview": self.preview.__dict__ if self.preview else None,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "updated_at": self.updated_at,
            "approved_at": self.approved_at,
            "rejected_at": self.rejected_at,
            "applied_at": self.applied_at,
            "failed_at": self.failed_at,
            "approval_hash": self.approval_hash,
            "result_hash": self.result_hash,
            "error": self.error,
            "error_code": self.error_code.value if self.error_code else None,
            "actor": self.actor,
            "audit_refs": self.audit_refs,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChangeProposal":
        """Deserialize proposal from dictionary."""
        proposal = cls(
            proposal_id=data["proposal_id"],
            operation=ChangeOperation(data["operation"]),
            state=ProposalState(data["state"]),
            workspace_root=data["workspace_root"],
            workspace_name=data["workspace_name"],
            source_path=data.get("source_path"),
            destination_path=data.get("destination_path"),
            content=data.get("content"),
            content_hash=data.get("content_hash"),
            source_hash=data.get("source_hash"),
            proposal_hash=data["proposal_hash"],
            created_at=data["created_at"],
            expires_at=data.get("expires_at"),
            updated_at=data["updated_at"],
            approved_at=data.get("approved_at"),
            rejected_at=data.get("rejected_at"),
            applied_at=data.get("applied_at"),
            failed_at=data.get("failed_at"),
            approval_hash=data.get("approval_hash"),
            result_hash=data.get("result_hash"),
            error=data.get("error"),
            error_code=ChangeErrorCode(data["error_code"]) if data.get("error_code") else None,
            actor=data.get("actor", "system"),
            audit_refs=data.get("audit_refs", []),
        )
        if data.get("preview"):
            proposal.preview = ChangePreview(**data["preview"])
        return proposal