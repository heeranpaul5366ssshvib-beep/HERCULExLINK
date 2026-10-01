"""
============================================
HERCULE AI Operating System
Module: Workspace Manager
Author: HERCULE Team
License: MIT
============================================

Centralized workspace scope management for P1 Selected-Content Understanding.

Provides:
- Explicit workspace selection and scope enforcement
- Read-only operations within workspace boundary
- Path traversal protection (no `..`, no absolute escapes, no similar-prefix)
- Symlink/junction escape prevention
- Sensitive file policy (deny .env, private keys, credentials)
- Bounded reads with truncation metadata
- Consulted-file tracking for audit transparency

All filesystem access through this module must pass through the centralized
validation path. This is the single source of truth for workspace boundaries.
"""

from __future__ import annotations

import logging
import os
import stat
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, List, Dict

logger = logging.getLogger("HERCULE.WorkspaceManager")


@dataclass(frozen=True)
class WorkspaceScope:
    """Immutable workspace scope definition."""
    root: Path
    name: str
    selected_at: float
    selected_by: str = "user"


@dataclass
class AccessResult:
    """Result of a workspace access attempt."""
    allowed: bool
    path: Optional[Path] = None
    workspace_relative: Optional[str] = None
    reason: str = ""
    denial_category: str = ""  # "no_workspace", "traversal", "absolute_escape", "similar_prefix", "symlink_escape", "sensitive_file", "size_limit", "not_found"
    truncation: Optional[Dict[str, Any]] = None


@dataclass
class ConsultedFileRecord:
    """Record of a file access for audit transparency."""
    workspace_relative: str
    operation: str  # "read", "list"
    allowed: bool
    timestamp: float
    truncation: Optional[Dict[str, Any]] = None
    denial_category: str = ""
    denial_reason: str = ""


# Sensitive file patterns - deny before reading where possible
SENSITIVE_PATTERNS = (
    ".env",
    ".env.*",
    "id_rsa",
    "id_ed25519",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.crt",
    "*.cer",
    "*.p7b",
    "*.p7c",
    "*.der",
    "ssh_host_*_key",
    "authorized_keys",
    "known_hosts",
    "config",  # ssh config
    "credentials",
    "credentials.*",
    "secrets",
    "secrets.*",
    "*.secret",
    "*.token",
    "*.credential",
    "aws_credentials",
    "gcp_credentials",
    "azure_credentials",
    "kubeconfig",
    ".netrc",
    ".pgpass",
    ".dockercfg",
    ".docker/config.json",
)


# Default read limits
DEFAULT_MAX_FILE_SIZE = 1024 * 1024  # 1 MB
DEFAULT_MAX_LINES = 5000
DEFAULT_MAX_CHARS = 500_000  # 500 KB


def _is_sensitive_file(path: Path) -> bool:
    """Check if a file matches sensitive patterns."""
    name = path.name.lower()
    for pattern in SENSITIVE_PATTERNS:
        if pattern.startswith("*."):
            ext = pattern[1:]
            if name.endswith(ext):
                return True
        elif pattern.endswith("*"):
            prefix = pattern[:-1]
            if name.startswith(prefix):
                return True
        elif "*" in pattern:
            prefix, suffix = pattern.split("*", 1)
            if name.startswith(prefix) and name.endswith(suffix):
                return True
        else:
            if name == pattern.lower():
                return True
    return False


def _matches_sensitive(path: Path) -> Optional[str]:
    """Return the matched sensitive pattern name if file is sensitive, else None."""
    name = path.name.lower()
    for pattern in SENSITIVE_PATTERNS:
        if pattern.startswith("*."):
            ext = pattern[1:]
            if name.endswith(ext):
                return pattern
        elif pattern.endswith("*"):
            prefix = pattern[:-1]
            if name.startswith(prefix):
                return pattern
        elif "*" in pattern:
            prefix, suffix = pattern.split("*", 1)
            if name.startswith(prefix) and name.endswith(suffix):
                return pattern
        else:
            if name == pattern.lower():
                return pattern
    return None


def _is_binary_file(path: Path, sample_size: int = 512) -> bool:
    """Heuristic check if file is binary."""
    try:
        with open(path, "rb") as f:
            sample = f.read(sample_size)
        if b"\x00" in sample:
            return True
        # Check for high proportion of non-text bytes
        text_chars = sum(1 for b in sample if 32 <= b <= 126 or b in (9, 10, 13))
        if len(sample) > 0 and text_chars / len(sample) < 0.7:
            return True
    except Exception:
        pass
    return False


class WorkspaceManager:
    """
    Centralized workspace scope manager.

    All filesystem access for user-selected content must go through this class.
    Provides read-only operations with strict scope enforcement.
    """

    def __init__(self, audit_manager=None):
        self._scope: Optional[WorkspaceScope] = None
        self._audit = audit_manager
        self._consulted_files: List[ConsultedFileRecord] = []
        self._max_file_size = DEFAULT_MAX_FILE_SIZE
        self._max_lines = DEFAULT_MAX_LINES
        self._max_chars = DEFAULT_MAX_CHARS
        self._enforce_readonly = True

    @property
    def active_scope(self) -> Optional[WorkspaceScope]:
        return self._scope

    @property
    def is_workspace_selected(self) -> bool:
        return self._scope is not None

    def select_workspace(self, path: str, name: Optional[str] = None, selected_by: str = "user") -> AccessResult:
        """
        Explicitly select a workspace root.

        Args:
            path: Absolute or relative path to workspace root
            name: Optional friendly name for the workspace
            selected_by: Who/what selected this workspace

        Returns:
            AccessResult with allowed=True if successful, denial info if not
        """
        try:
            candidate = Path(path).resolve()
        except Exception as e:
            return AccessResult(
                allowed=False,
                reason=f"invalid path: {e}",
                denial_category="invalid_path"
            )

        if not candidate.exists():
            return AccessResult(
                allowed=False,
                reason=f"workspace does not exist: {candidate}",
                denial_category="not_found"
            )

        if not candidate.is_dir():
            return AccessResult(
                allowed=False,
                reason=f"workspace must be a directory: {candidate}",
                denial_category="not_directory"
            )

        workspace_name = name or candidate.name
        self._scope = WorkspaceScope(
            root=candidate,
            name=workspace_name,
            selected_at=time.time(),
            selected_by=selected_by
        )

        # Log workspace selection
        if self._audit:
            self._audit.log(f"Workspace selected: {workspace_name} at {candidate}")

        return AccessResult(
            allowed=True,
            path=candidate,
            workspace_relative=".",
            reason=f"Workspace '{workspace_name}' selected"
        )

    def clear_workspace(self) -> None:
        """Clear the active workspace selection."""
        if self._scope and self._audit:
            self._audit.log(f"Workspace cleared: {self._scope.name}")
        self._scope = None

    def _resolve_in_workspace(self, path: str) -> AccessResult:
        """
        Centralized path validation - the single source of truth for scope enforcement.

        Returns AccessResult with resolved path if allowed, denial info if not.
        """
        if not self._scope:
            return AccessResult(
                allowed=False,
                reason="no workspace selected",
                denial_category="no_workspace"
            )

        workspace_root = self._scope.root
        cleaned = path.strip().strip('"').strip("'")

        try:
            # Resolve candidate path
            candidate = Path(cleaned) if Path(cleaned).is_absolute() else (workspace_root / cleaned)
            resolved_candidate = candidate.resolve()
        except Exception as e:
            return AccessResult(
                allowed=False,
                reason=f"path resolution failed: {e}",
                denial_category="resolution_failed"
            )

        try:
            # Check containment using resolved paths (safe against traversal)
            relative = resolved_candidate.relative_to(workspace_root.resolve())
        except ValueError:
            return AccessResult(
                allowed=False,
                reason=f"path escapes workspace: {path}",
                denial_category="traversal"
            )

        # Check for symlink/junction escape
        try:
            # On Windows, check for junctions
            if os.name == "nt":
                # Check if any part of the path is a junction
                for part in resolved_candidate.parents:
                    try:
                        if part.is_symlink() or (hasattr(os, 'readlink') and os.readlink(part) != part):
                            target = Path(os.readlink(part)).resolve()
                            if not target.is_relative_to(workspace_root.resolve()):
                                return AccessResult(
                                    allowed=False,
                                    reason=f"symlink/junction escapes workspace: {part}",
                                    denial_category="symlink_escape"
                                )
                    except Exception:
                        pass
            else:
                # Unix-like: check symlinks
                for part in resolved_candidate.parents:
                    try:
                        if part.is_symlink():
                            target = Path(os.readlink(part)).resolve()
                            if not target.is_relative_to(workspace_root.resolve()):
                                return AccessResult(
                                    allowed=False,
                                    reason=f"symlink escapes workspace: {part}",
                                    denial_category="symlink_escape"
                                )
                    except Exception:
                        pass
        except Exception:
            pass  # Best effort - if we can't check, continue

        return AccessResult(
            allowed=True,
            path=resolved_candidate,
            workspace_relative=str(relative),
            reason="access allowed"
        )

    def _check_sensitive(self, path: Path) -> Optional[str]:
        """Check if file matches sensitive pattern, return pattern name if so."""
        return _matches_sensitive(path)

    def _check_size_limit(self, path: Path) -> Optional[Dict[str, Any]]:
        """Check file size against limits, return truncation info if exceeds."""
        try:
            size = path.stat().st_size
        except Exception:
            return None

        if size > self._max_file_size:
            return {
                "allowed": False,
                "truncated": True,
                "reason": "size_limit",
                "file_size": size,
                "limit": self._max_file_size,
                "message": f"File size {size} bytes exceeds limit {self._max_file_size} bytes",
                "denial_category": "size_limit"
            }
        return None

def _read_text_bounded(self, path: Path) -> tuple[str, Optional[Dict[str, Any]]]:
        """Read text file with line/char limits, return content and truncation info."""
        truncation_info = {"truncated": False}

        # Check file size first
        size_check = self._check_size_limit(path)
        if size_check:
            return "", {**size_check, "allowed": False}

        # Check if binary
        if _is_binary_file(path):
            return "", {"allowed": False, "truncated": True, "reason": "binary_file", "message": "File appears to be binary", "denial_category": "binary_file"}

        lines = []
        total_chars = 0
        truncated = False

        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if len(lines) >= self._max_lines:
                        truncated = True
                        break
                    if total_chars + len(line) > self._max_chars:
                        truncated = True
                        break
                    lines.append(line)
                    total_chars += len(line)
        except Exception as e:
            return "", {"allowed": False, "truncated": True, "reason": "read_error", "error": str(e)}

        content = "".join(lines)

        if truncated:
            truncation_info = {
                "truncated": True,
                "reason": "line_or_char_limit",
                "lines_read": len(lines),
                "max_lines": self._max_lines,
                "chars_read": total_chars,
                "max_chars": self._max_chars,
                "message": f"File truncated: read {len(lines)} lines ({total_chars} chars) of max {self._max_lines} lines / {self._max_chars} chars"
            }

        return content, truncation_info if truncated else None

    def _record_access(self, workspace_relative: str, operation: str, allowed: bool,
                       truncation: Optional[Dict[str, Any]] = None,
                       denial_category: str = "", denial_reason: str = "") -> None:
        """Record file access for audit transparency."""
        record = ConsultedFileRecord(
            workspace_relative=workspace_relative,
            operation=operation,
            allowed=allowed,
            timestamp=time.time(),
            truncation=truncation,
            denial_category=denial_category,
            denial_reason=denial_reason
        )
        self._consulted_files.append(record)

        # Also log to audit manager if available
        if self._audit:
            if allowed:
                self._audit.log(f"File {operation}: {workspace_relative}" + (f" [truncated]" if truncation and truncation.get("truncated") else ""))
            else:
                self._audit.log(f"File {operation} DENIED: {workspace_relative} ({denial_category}: {denial_reason})")

    # Public read-only API

    def read_file(self, path: str) -> AccessResult:
        """
        Read a text file within the workspace.

        Returns AccessResult with content if allowed, denial info if not.
        """
        # Resolve and validate path
        resolved = self._resolve_in_workspace(path)
        if not resolved.allowed:
            self._record_access(
                path, "read", False,
                denial_category=resolved.denial_category,
                denial_reason=resolved.reason
            )
            return resolved

        target_path = resolved.path

        # Check sensitive file policy
        sensitive_pattern = self._check_sensitive(target_path)
        if sensitive_pattern:
            self._record_access(
                resolved.workspace_relative, "read", False,
                denial_category="sensitive_file",
                denial_reason=f"sensitive file pattern: {sensitive_pattern}"
            )
            return AccessResult(
                allowed=False,
                reason=f"sensitive file denied: {sensitive_pattern}",
                denial_category="sensitive_file",
                workspace_relative=resolved.workspace_relative
            )

        # Check file exists
        if not target_path.exists():
            self._record_access(
                resolved.workspace_relative, "read", False,
                denial_category="not_found",
                denial_reason="file not found"
            )
            return AccessResult(
                allowed=False,
                reason="file not found",
                denial_category="not_found",
                workspace_relative=resolved.workspace_relative
            )

        if not target_path.is_file():
            self._record_access(
                resolved.workspace_relative, "read", False,
                denial_category="not_file",
                denial_reason="path is not a file"
            )
            return AccessResult(
                allowed=False,
                reason="path is not a file",
                denial_category="not_file",
                workspace_relative=resolved.workspace_relative
            )

        # Read with bounds
        content, truncation = self._read_text_bounded(target_path)

        # Check if read was denied (binary, size limit, etc.)
        if isinstance(truncation, dict) and truncation.get("allowed") is False:
            self._record_access(
                resolved.workspace_relative, "read", False,
                denial_category=truncation.get("reason", "read_denied"),
                denial_reason=truncation.get("message", "read denied")
            )
            return AccessResult(
                allowed=False,
                reason=truncation.get("message", "read denied"),
                denial_category=truncation.get("reason", "read_denied"),
                workspace_relative=resolved.workspace_relative
            )

        # Record successful access
        self._record_access(
            resolved.workspace_relative, "read", True, truncation
        )

        return AccessResult(
            allowed=True,
            path=target_path,
            workspace_relative=resolved.workspace_relative,
            reason="read successful",
            truncation=truncation
        )

    def list_directory(self, path: str = ".") -> AccessResult:
        """
        List directory contents within the workspace.

        Returns AccessResult with list of entries if allowed.
        """
        resolved = self._resolve_in_workspace(path)
        if not resolved.allowed:
            self._record_access(
                path, "list", False,
                denial_category=resolved.denial_category,
                denial_reason=resolved.reason
            )
            return resolved

        target_path = resolved.path

        if not target_path.exists():
            self._record_access(
                resolved.workspace_relative, "list", False,
                denial_category="not_found",
                denial_reason="directory not found"
            )
            return AccessResult(
                allowed=False,
                reason="directory not found",
                denial_category="not_found",
                workspace_relative=resolved.workspace_relative
            )

        if not target_path.is_dir():
            self._record_access(
                resolved.workspace_relative, "list", False,
                denial_category="not_directory",
                denial_reason="path is not a directory"
            )
            return AccessResult(
                allowed=False,
                reason="path is not a directory",
                denial_category="not_directory",
                workspace_relative=resolved.workspace_relative
            )

        try:
            items = sorted(p.name for p in target_path.iterdir())
            self._record_access(
                resolved.workspace_relative, "list", True
            )
            return AccessResult(
                allowed=True,
                path=target_path,
                workspace_relative=resolved.workspace_relative,
                reason="list successful",
                truncation={"item_count": len(items)}
            )
        except Exception as e:
            return AccessResult(
                allowed=False,
                reason=f"list failed: {e}",
                denial_category="list_failed",
                workspace_relative=resolved.workspace_relative
            )

    def get_workspace_info(self) -> Optional[Dict[str, Any]]:
        """Get current workspace metadata."""
        if not self._scope:
            return None
        return {
            "name": self._scope.name,
            "root": str(self._scope.root),
            "selected_at": self._scope.selected_at,
            "selected_by": self._scope.selected_by
        }

    def get_consulted_files(self, clear: bool = False) -> List[ConsultedFileRecord]:
        """Get the list of files consulted in this session."""
        records = list(self._consulted_files)
        if clear:
            self._consulted_files.clear()
        return records

    def set_limits(self, max_file_size: Optional[int] = None,
                   max_lines: Optional[int] = None,
                   max_chars: Optional[int] = None) -> None:
        """Configure read limits (for testing or user preference)."""
        if max_file_size is not None:
            self._max_file_size = max_file_size
        if max_lines is not None:
            self._max_lines = max_lines
        if max_chars is not None:
            self._max_chars = max_chars

    def set_readonly_mode(self, enforce: bool = True) -> None:
        """Set read-only enforcement mode."""
        self._enforce_readonly = enforce


# Convenience function for creating a workspace manager with audit integration
def create_workspace_manager(audit_manager=None) -> WorkspaceManager:
    """Factory function to create a WorkspaceManager with optional audit integration."""
    return WorkspaceManager(audit_manager=audit_manager)