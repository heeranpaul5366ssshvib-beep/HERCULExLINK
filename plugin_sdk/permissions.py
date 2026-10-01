from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Plugin Permission Model & Approval System
--------------------------------------------
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from enum import Enum
import json
from pathlib import Path
from datetime import datetime, timezone
import hashlib

from plugin_sdk.manifest import PluginPermission


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    GRANTED = "granted"
    DENIED = "denied"
    REVOKED = "revoked"


@dataclass
class PermissionApproval:
    """Record of a permission approval for a specific plugin version."""
    plugin_id: str
    plugin_version: str
    permission: str
    status: ApprovalStatus
    granted_at: Optional[str] = None
    revoked_at: Optional[str] = None
    requested_by: str = "user"
    metadata: Dict[str, any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, any]:
        return {
            "plugin_id": self.plugin_id,
            "plugin_version": self.plugin_version,
            "permission": self.permission,
            "status": self.status.value,
            "granted_at": self.granted_at,
            "revoked_at": self.revoked_at,
            "requested_by": self.requested_by,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, any]) -> "PermissionApproval":
        return cls(
            plugin_id=data["plugin_id"],
            plugin_version=data["plugin_version"],
            permission=data["permission"],
            status=ApprovalStatus(data["status"]),
            granted_at=data.get("granted_at"),
            revoked_at=data.get("revoked_at"),
            requested_by=data.get("requested_by", "user"),
            metadata=data.get("metadata", {}),
        )


class PluginPermissionModel:
    """
    Explicit permission model for plugins.
    Permissions are independent capabilities - having NETWORK does not grant SHELL.
    """

    # Permissions that require explicit user approval
    SENSITIVE_PERMISSIONS: Set[str] = {
        PluginPermission.SHELL.value,
        PluginPermission.PROCESS_EXECUTION.value,
        PluginPermission.FILESYSTEM_WRITE.value,
        PluginPermission.SECRETS.value,
        PluginPermission.MICROPHONE.value,
        PluginPermission.CAMERA.value,
        PluginPermission.AUTOMATION.value,
    }

    def __init__(self, approvals_store: Optional[Path] = None):
        self._approvals: Dict[str, PermissionApproval] = {}
        self._store_path = approvals_store or Path("config/plugin_approvals.json")
        self._load_approvals()

    def _load_approvals(self) -> None:
        if self._store_path.exists():
            try:
                data = json.loads(self._store_path.read_text(encoding="utf-8"))
                for item in data.get("approvals", []):
                    approval = PermissionApproval.from_dict(item)
                    key = self._approval_key(approval.plugin_id, approval.plugin_version, approval.permission)
                    self._approvals[key] = approval
            except Exception:
                pass

    def _save_approvals(self) -> None:
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "approvals": [a.to_dict() for a in self._approvals.values()],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._store_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @staticmethod
    def _approval_key(plugin_id: str, plugin_version: str, permission: str) -> str:
        return f"{plugin_id}@{plugin_version}:{permission}"

    def is_sensitive(self, permission: str) -> bool:
        return permission in self.SENSITIVE_PERMISSIONS

    def is_granted(self, plugin_id: str, plugin_version: str, permission: str) -> bool:
        # Non-sensitive permissions are auto-granted
        if not self.is_sensitive(permission):
            return True
        key = self._approval_key(plugin_id, plugin_version, permission)
        approval = self._approvals.get(key)
        return approval is not None and approval.status == ApprovalStatus.GRANTED

    def request_approval(
        self,
        plugin_id: str,
        plugin_version: str,
        permission: str,
        requested_by: str = "user",
    ) -> PermissionApproval:
        key = self._approval_key(plugin_id, plugin_version, permission)
        if key in self._approvals:
            existing = self._approvals[key]
            if existing.status == ApprovalStatus.GRANTED:
                return existing
            # Re-request if previously denied or revoked
            existing.status = ApprovalStatus.PENDING
            existing.requested_by = requested_by
            return existing

        approval = PermissionApproval(
            plugin_id=plugin_id,
            plugin_version=plugin_version,
            permission=permission,
            status=ApprovalStatus.PENDING,
            requested_by=requested_by,
        )
        self._approvals[key] = approval
        self._save_approvals()
        return approval

    def grant_approval(
        self,
        plugin_id: str,
        plugin_version: str,
        permission: str,
    ) -> bool:
        key = self._approval_key(plugin_id, plugin_version, permission)
        approval = self._approvals.get(key)
        if not approval:
            # Auto-create approval record if it doesn't exist
            approval = PermissionApproval(
                plugin_id=plugin_id,
                plugin_version=plugin_version,
                permission=permission,
                status=ApprovalStatus.PENDING,
                requested_by="user",
            )
            self._approvals[key] = approval
        approval.status = ApprovalStatus.GRANTED
        approval.granted_at = datetime.now(timezone.utc).isoformat()
        self._save_approvals()
        return True

    def deny_approval(
        self,
        plugin_id: str,
        plugin_version: str,
        permission: str,
    ) -> bool:
        key = self._approval_key(plugin_id, plugin_version, permission)
        approval = self._approvals.get(key)
        if approval:
            approval.status = ApprovalStatus.DENIED
            self._save_approvals()
            return True
        return False

    def revoke_approval(
        self,
        plugin_id: str,
        plugin_version: str,
        permission: str,
    ) -> bool:
        key = self._approval_key(plugin_id, plugin_version, permission)
        approval = self._approvals.get(key)
        if approval and approval.status == ApprovalStatus.GRANTED:
            approval.status = ApprovalStatus.REVOKED
            approval.revoked_at = datetime.now(timezone.utc).isoformat()
            self._save_approvals()
            return True
        return False

    def get_approval(self, plugin_id: str, plugin_version: str, permission: str) -> Optional[PermissionApproval]:
        key = self._approval_key(plugin_id, plugin_version, permission)
        return self._approvals.get(key)

    def get_all_approvals(self, plugin_id: str, plugin_version: str) -> List[PermissionApproval]:
        prefix = f"{plugin_id}@{plugin_version}:"
        return [a for k, a in self._approvals.items() if k.startswith(prefix)]

    def get_pending_approvals(self) -> List[PermissionApproval]:
        return [a for a in self._approvals.values() if a.status == ApprovalStatus.PENDING]

    def check_permission_set_changed(
        self,
        plugin_id: str,
        old_version: str,
        new_version: str,
        old_permissions: List[str],
        new_permissions: List[str],
    ) -> List[str]:
        """
        Check if plugin update requires new approvals.
        Returns list of newly requested sensitive permissions.
        """
        new_sensitive = set(p for p in new_permissions if self.is_sensitive(p))
        old_sensitive = set(p for p in old_permissions if self.is_sensitive(p))
        newly_requested = new_sensitive - old_sensitive

        # Also check if version changed - if so, all previous approvals are invalidated
        if old_version != new_version:
            # Invalidate old approvals
            for perm in old_sensitive:
                self.revoke_approval(plugin_id, old_version, perm)
            return list(new_sensitive)

        return list(newly_requested)


class PluginPermissionChecker:
    """Runtime permission checker for plugin context."""

    def __init__(
        self,
        plugin_id: str,
        plugin_version: str,
        declared_permissions: List[str],
        permission_model: PluginPermissionModel,
    ):
        self._plugin_id = plugin_id
        self._plugin_version = plugin_version
        self._declared = set(declared_permissions)
        self._model = permission_model

    def _is_granted(self, permission: str) -> bool:
        """Check if permission is currently granted (dynamic check)."""
        if permission not in self._declared:
            return False
        return self._model.is_granted(self._plugin_id, self._plugin_version, permission)

    def has(self, permission: str) -> bool:
        return self._is_granted(permission)

    def check(self, permission: str) -> bool:
        if permission not in self._declared:
            raise PermissionError(f"Plugin '{self._plugin_id}' does not declare permission: {permission}")
        if not self._is_granted(permission):
            raise PermissionError(f"Plugin '{self._plugin_id}' does not have granted permission: {permission}")
        return True

    def get_granted(self) -> List[str]:
        return [p for p in self._declared if self._is_granted(p)]

    def get_declared(self) -> List[str]:
        return list(self._declared)

    def get_pending(self) -> List[str]:
        return [p for p in self._declared if not self._is_granted(p) and self._model.is_sensitive(p)]