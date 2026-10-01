"""
--------------------------------------------
HERCULE AI Operating System
Module: File Ability
Author: Heeran Paul
License: MIT
--------------------------------------------

File Ability with P1 Selected-Content Understanding:
- Read-only mode using WorkspaceManager for scope enforcement
- Sensitive file protection
- Bounded reads with truncation metadata
- Consulted-file tracking for audit transparency
- Write operations preserved for backward compatibility (not part of P1)
"""

from __future__ import annotations

from pathlib import Path

import re as _re

from abilities.base_ability import BaseAbility

# Import WorkspaceManager for P1 scope enforcement
try:
    from workspace_manager import WorkspaceManager, create_workspace_manager
except Exception:
    WorkspaceManager = None
    create_workspace_manager = None

import re as _re
from pathlib import Path


def _workspace() -> Path:
    """Sandbox root for file operations (legacy, for write operations).

    Development: the process working directory at call time. Installed
    (frozen) app: a per-user workspace directory, since the install
    location (Program Files) and the launch cwd are not writable.
    """
    try:
        from system.paths import is_frozen, user_data_dir
        if is_frozen():
            workspace = user_data_dir() / "workspace"
            workspace.mkdir(parents=True, exist_ok=True)
            return workspace
    except Exception:
        pass
    return Path.cwd()


def _resolve(path: str) -> Path:
    """Resolve inside the workspace sandbox (no absolute escapes)."""
    cleaned = path.strip().strip('"').strip("'")
    workspace = _workspace()
    candidate = (Path(cleaned) if Path(cleaned).is_absolute()
                  else workspace / cleaned).resolve()
    try:
        candidate.relative_to(workspace.resolve())
    except ValueError:
        raise ValueError(f"path escapes workspace sandbox: {path!r}")
    return candidate


class FileAbility(BaseAbility):

    def __init__(self):

        super().__init__(

            "files",

            "Read, write, and list files inside the workspace sandbox. "
            "P1: Read-only mode with explicit workspace scope enforcement, "
            "sensitive file protection, bounded reads, and audit logging.",

            capability="FILE_READ",
            inputs={"operation": "read|write|list", "path": "workspace-relative path",
                    "data": "content for write", "readonly": "enable read-only P1 mode"},
            outputs={"content": "file text or listing", "consulted_files": "audit trail"},
            permissions=["FILE_READ", "FILE_WRITE"],
            environments={"default"},
            verification="content returned and non-empty / target exists",
            timeout_s=15,
            risk="MEDIUM",

        )
        
        # P1: Workspace manager for read-only scope enforcement
        self._workspace_manager = None
        self._readonly_mode = False
        if create_workspace_manager:
            try:
                # Get audit manager from runtime if available
                from security.auditing.audit_manager import AuditManager
                audit = AuditManager()
                self._workspace_manager = create_workspace_manager(audit)
            except Exception:
                pass

    ##################################################

    def validate_input(self, task, **kwargs):
        if isinstance(task, dict):
            if task.get("operation") in ("read", "write", "list") and task.get("path"):
                return ""
            if task.get("operation") or task.get("path"):
                return "payload needs operation (read|write|list) and path"
            return ""
        text = str(task or "")
        if not text.strip() and not kwargs.get("path"):
            return "empty file request"
        return ""

    def _ensure_workspace_manager(self):
        """Lazy initialization of workspace manager."""
        if self._workspace_manager is None and create_workspace_manager:
            try:
                from security.auditing.audit_manager import AuditManager
                audit = AuditManager()
                self._workspace_manager = create_workspace_manager(audit)
            except Exception:
                pass
        return self._workspace_manager

    def _get_workspace_root(self) -> Path:
        """Get the workspace root for P1 operations."""
        wm = self._ensure_workspace_manager()
        if wm and wm.active_scope:
            return wm.active_scope.root
        return _workspace()

    def _resolve_p1(self, path: str) -> Path:
        """P1 scope-aware resolution using WorkspaceManager."""
        wm = self._ensure_workspace_manager()
        if wm and wm.active_scope:
            workspace_root = wm.active_scope.root
            cleaned = path.strip().strip('"').strip("'")
            candidate = (Path(path) if Path(path).is_absolute()
                          else workspace_root / cleaned).resolve()
            try:
                candidate.relative_to(workspace_root.resolve())
            except ValueError:
                raise ValueError(f"path escapes workspace sandbox: {path!r}")
            return candidate
        # Fallback to legacy for backward compatibility
        return _resolve(path)

    ##################################################

    def validate_input(self, task, **kwargs):
        if isinstance(task, dict):
            if task.get("operation") in ("read", "write", "list") and task.get("path"):
                return ""
            if task.get("operation") or task.get("path"):
                return "payload needs operation (read|write|list) and path"
            return ""
        text = str(task or "")
        if not text.strip() and not kwargs.get("path"):
            return "empty file request"
        return ""

    def execute(

        self,

        task="",

        context=None,

        **kwargs,

    ):
        operation = str(kwargs.pop("operation", "") or "").lower()
        path = str(kwargs.pop("path", "") or "")
        data = kwargs.pop("data", kwargs.pop("content", ""))
        readonly = kwargs.pop("readonly", self._readonly_mode)
        text = task if isinstance(task, str) else ""

        if isinstance(task, dict):
            operation = operation or str(task.get("operation", "")).lower()
            path = path or str(task.get("path", ""))
            data = data if data != "" else task.get("data", task.get("content", ""))
            readonly = readonly or task.get("readonly", self._readonly_mode)
            text = str(task.get("description", text or ""))

        if not operation:
            lowered = f"{text} {path}".lower()
            # v1.1: write intent covers any workspace file artifact (.py,
            # .md, .json, ...) — not just .txt — so resolved multi-step
            # references ("write ... into test.py") route correctly.
            # Legacy ".txt"/"file" behavior is preserved byte-identically.
            has_file_artifact = ("file" in lowered or bool(
                _re.search(r"\.(txt|md|json|py|log|csv)\b", lowered)))
            if any(k in lowered for k in ("create", "write", "save")) and has_file_artifact:
                operation = "write"
            elif "list" in lowered and ("file" in lowered or "director" in lowered):
                operation = "list"
            else:
                operation = "read"
        if not path:
            match = _re.search(r"[\w\-./\\]+\.(txt|md|json|py|log|csv)", f"{text} {path}")
            path = match.group(0).strip("\"'") if match else path
        if operation in ("read", "write") and not path:
            # Never hallucinate a filename: without an explicit path the
            # request is underspecified — fail honestly so the pipeline can
            # fall back to another provider or report clearly.
            return {"status": "failed", "operation": operation,
                    "error": "no file path specified"}
        if operation == "write" and (data == "" or data is None):
            quoted = _re.search(r"['\"]([^'\"]+)['\"]", text)
            content_match = _re.search(r"(?i)content\s+(?:of\s+)?(?:is\s+)?(.+)$", text)
            data = (quoted.group(1) if quoted else
                    (content_match.group(1).strip() if content_match else "Hello from HERCULE"))
        
        # P1: Read-only mode uses WorkspaceManager for scope enforcement
        if operation in ("read", "list") and readonly:
            wm = self._ensure_workspace_manager()
            if not wm:
                return {"status": "failed", "operation": operation,
                        "error": "P1 workspace manager not available"}
            
            if not wm.active_scope:
                return {"status": "failed", "operation": operation,
                        "error": "no workspace selected for P1 read-only access"}
            
            try:
                if operation == "read":
                    result = wm.read_file(path)
                elif operation == "list":
                    result = wm.list_directory(path)
                else:
                    return {"status": "failed", "operation": operation,
                            "error": f"unsupported read-only operation: {operation}"}
                
                if result.allowed:
                    response = {
                        "status": "success",
                        "operation": operation,
                        "path": result.workspace_relative,
                        "content": result.path.read_text(encoding="utf-8", errors="ignore") if operation == "read" else "\n".join(sorted(p.name for p in result.path.iterdir()))
                    }
                    if result.truncation:
                        response["truncation"] = result.truncation
                    return response
                else:
                    return {
                        "status": "failed",
                        "operation": operation,
                        "error": result.reason,
                        "denial_category": result.denial_category,
                        "workspace_relative": result.workspace_relative
                    }
            except Exception as error:
                return {"status": "failed", "operation": operation, "error": str(error)}

        # Legacy path for write operations and non-readonly reads
        try:
            target = _resolve(path)
        except Exception as error:
            return {"status": "failed", "operation": operation, "error": str(error)}

        try:
            if operation == "write":
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(str(data), encoding="utf-8")
                return {"status": "success", "operation": "write",
                        "path": str(target.relative_to(_workspace().resolve())),
                        "content": str(data)}
            if operation == "list":
                directory = target if target.is_dir() else target.parent
                items = sorted(p.name for p in directory.iterdir()) if directory.is_dir() else []
                return {"status": "success", "operation": "list",
                        "path": str(directory), "content": "\n".join(items)}
            if not target.exists():
                return {"status": "failed", "operation": "read",
                        "path": str(path), "error": f"file not found: {path}"}
            content = target.read_text(encoding="utf-8", errors="ignore")
            return {"status": "success", "operation": "read",
                    "path": str(target.relative_to(_workspace().resolve())),
                    "content": content}
        except Exception as error:
            return {"status": "failed", "operation": operation,
                    "path": str(path), "error": str(error)}

    ##################################################

    def write(

        self,

        path,

        data,

    ):

        result = self.execute({"operation": "write", "path": path, "data": data})
        if result.get("status") != "success":
            raise RuntimeError(result.get("error", "write failed"))
        return result.get("content", "")

    def set_readonly_mode(self, enabled: bool) -> None:
        """Enable or disable P1 read-only mode."""
        self._readonly_mode = enabled
        if enabled:
            self._ensure_workspace_manager()

    def select_workspace(self, path: str, name: str = "") -> dict:
        """Select workspace for P1 read-only operations."""
        wm = self._ensure_workspace_manager()
        if not wm:
            return {"status": "failed", "error": "P1 workspace manager not available"}
        result = wm.select_workspace(path, name=name or "user-selected")
        if result.allowed:
            self._readonly_mode = True
            return {"status": "success", "workspace": result.workspace_relative, "root": str(wm.active_scope.root)}
        return {"status": "failed", "error": result.reason, "denial_category": result.denial_category}

    def clear_workspace(self) -> dict:
        """Clear the active workspace selection."""
        wm = self._ensure_workspace_manager()
        if wm:
            wm.clear_workspace()
            self._readonly_mode = False
            return {"status": "success", "message": "workspace cleared"}
        return {"status": "failed", "error": "workspace manager not available"}

    def get_workspace_info(self) -> dict:
        """Get current workspace metadata."""
        wm = self._ensure_workspace_manager()
        if wm and wm.active_scope:
            info = wm.get_workspace_info()
            info["readonly_mode"] = self._readonly_mode
            return info
        return {"status": "no_workspace", "readonly_mode": self._readonly_mode}

    def get_consulted_files(self, clear: bool = False) -> list:
        """Get the list of files consulted in this session (audit trail)."""
        wm = self._ensure_workspace_manager()
        if wm:
            return [r.__dict__ for r in wm.get_consulted_files(clear=clear)]
        return []

    def set_workspace_limits(self, max_file_size: int = None, max_lines: int = None, max_chars: int = None) -> dict:
        """Configure read limits for P1 operations."""
        wm = self._ensure_workspace_manager()
        if wm:
            wm.set_limits(max_file_size, max_lines, max_chars)
            return {"status": "success", "limits": {
                "max_file_size": max_file_size,
                "max_lines": max_lines,
                "max_chars": max_chars
            }}
        return {"status": "failed", "error": "workspace manager not available"}

    def set_readonly_enforcement(self, enforce: bool = True) -> None:
        """Set read-only enforcement mode."""
        self._readonly_mode = enforce
        wm = self._ensure_workspace_manager()
        if wm:
            wm.set_readonly_mode(enforce)

    ##################################################
    # P2: Change Proposal Creation Methods
    ##################################################

    def _ensure_change_proposal_manager(self):
        """Lazy initialization of change proposal manager."""
        if not hasattr(self, '_change_proposal_manager') or self._change_proposal_manager is None:
            try:
                from change_proposal_manager import ChangeProposalManager
                from security.auditing.audit_manager import AuditManager
                audit = AuditManager()
                wm = self._ensure_workspace_manager()
                self._change_proposal_manager = ChangeProposalManager(wm, audit)
            except Exception:
                pass
        return self._change_proposal_manager

    def create_text_file_proposal(
        self,
        destination_path: str,
        content: str = "",
        workspace_root: Optional[str] = None,
        workspace_name: Optional[str] = None,
        actor: str = "system",
        expires_in: Optional[float] = None,
    ) -> dict:
        """Create a CREATE_TEXT_FILE proposal."""
        cpm = self._ensure_change_proposal_manager()
        if not cpm:
            return {"status": "failed", "error": "Change proposal manager not available"}
        
        proposal = cpm.create_proposal(
            operation="create_text_file",
            destination_path=destination_path,
            content=content,
            workspace_root=workspace_root,
            workspace_name=workspace_name,
            actor=actor,
            expires_in=expires_in,
        )
        return proposal.to_dict()

    def edit_text_file_proposal(
        self,
        source_path: str,
        content: str,
        workspace_root: Optional[str] = None,
        workspace_name: Optional[str] = None,
        actor: str = "system",
        expires_in: Optional[float] = None,
    ) -> dict:
        """Create an EDIT_TEXT_FILE proposal."""
        cpm = self._ensure_change_proposal_manager()
        if not cpm:
            return {"status": "failed", "error": "Change proposal manager not available"}
        
        proposal = cpm.create_proposal(
            operation="edit_text_file",
            source_path=source_path,
            content=content,
            workspace_root=workspace_root,
            workspace_name=workspace_name,
            actor=actor,
            expires_in=expires_in,
        )
        return proposal.to_dict()

    def move_or_rename_proposal(
        self,
        source_path: str,
        destination_path: str,
        workspace_root: Optional[str] = None,
        workspace_name: Optional[str] = None,
        actor: str = "system",
        expires_in: Optional[float] = None,
    ) -> dict:
        """Create a MOVE_OR_RENAME proposal."""
        cpm = self._ensure_change_proposal_manager()
        if not cpm:
            return {"status": "failed", "error": "Change proposal manager not available"}
        
        proposal = cpm.create_proposal(
            operation="move_or_rename",
            source_path=source_path,
            destination_path=destination_path,
            workspace_root=workspace_root,
            workspace_name=workspace_name,
            actor=actor,
            expires_in=expires_in,
        )
        return proposal.to_dict()

    def submit_proposal(self, proposal_id: str) -> dict:
        """Submit a draft proposal for approval."""
        cpm = self._ensure_change_proposal_manager()
        if not cpm:
            return {"status": "failed", "error": "Change proposal manager not available"}
        
        try:
            proposal = cpm.submit_for_approval(proposal_id)
            return proposal.to_dict()
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    def approve_proposal(self, proposal_id: str, actor: str = "user") -> dict:
        """Approve a pending proposal."""
        cpm = self._ensure_change_proposal_manager()
        if not cpm:
            return {"status": "failed", "error": "Change proposal manager not available"}
        
        try:
            proposal = cpm.approve(proposal_id, actor)
            return proposal.to_dict()
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    def reject_proposal(self, proposal_id: str, actor: str = "user", reason: str = "") -> dict:
        """Reject a pending proposal."""
        cpm = self._ensure_change_proposal_manager()
        if not cpm:
            return {"status": "failed", "error": "Change proposal manager not available"}
        
        try:
            proposal = cpm.reject(proposal_id, actor, reason)
            return proposal.to_dict()
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    def cancel_proposal(self, proposal_id: str, actor: str = "user") -> dict:
        """Cancel a draft or pending proposal."""
        cpm = self._ensure_change_proposal_manager()
        if not cpm:
            return {"status": "failed", "error": "Change proposal manager not available"}
        
        try:
            proposal = cpm.cancel(proposal_id, actor)
            return proposal.to_dict()
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    def apply_proposal(self, proposal_id: str) -> dict:
        """Apply an approved proposal."""
        cpm = self._ensure_change_proposal_manager()
        if not cpm:
            return {"status": "failed", "error": "Change proposal manager not available"}
        
        try:
            proposal = cpm.apply(proposal_id)
            return proposal.to_dict()
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    def get_proposal(self, proposal_id: str) -> dict:
        """Get a proposal by ID."""
        cpm = self._ensure_change_proposal_manager()
        if not cpm:
            return {"status": "failed", "error": "Change proposal manager not available"}
        
        proposal = cpm.get_proposal(proposal_id)
        if not proposal:
            return {"status": "failed", "error": "Proposal not found"}
        return proposal.to_dict()

    def get_proposal_preview(self, proposal_id: str) -> dict:
        """Get preview for a proposal."""
        cpm = self._ensure_change_proposal_manager()
        if not cpm:
            return {"status": "failed", "error": "Change proposal manager not available"}
        
        preview = cpm.get_proposal_preview(proposal_id)
        if not preview:
            return {"status": "failed", "error": "Preview not available"}
        return {"status": "success", "preview": preview.__dict__}

    def list_proposals(self, workspace_root: Optional[str] = None, state: Optional[str] = None) -> dict:
        """List proposals, optionally filtered by workspace and state."""
        cpm = self._ensure_change_proposal_manager()
        if not cpm:
            return {"status": "failed", "error": "Change proposal manager not available"}
        
        if workspace_root and state:
            proposals = cpm.get_proposals_by_state(state, workspace_root)
        elif workspace_root:
            proposals = cpm.get_proposals_by_workspace(workspace_root)
        elif state:
            proposals = cpm.get_proposals_by_state(state, workspace_root)
        else:
            proposals = list(cpm._proposals.values())
        
        return {"status": "success", "proposals": [p.to_dict() for p in proposals]}

    def expire_stale_proposals(self) -> dict:
        """Expire stale proposals."""
        cpm = self._ensure_change_proposal_manager()
        if not cpm:
            return {"status": "failed", "error": "Change proposal manager not available"}
        
        count = cpm.expire_stale_proposals()
        return {"status": "success", "expired_count": count}

    def cleanup_proposals(self, max_age_s: float = 3600.0) -> dict:
        """Clean up old proposals."""
        cpm = self._ensure_change_proposal_manager()
        if not cpm:
            return {"status": "failed", "error": "Change proposal manager not available"}
        
        count = cpm.cleanup_proposals(max_age_s)
        return {"status": "success", "removed_count": count}
