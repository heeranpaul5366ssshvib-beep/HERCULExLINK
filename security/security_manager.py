from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Security Manager
Author: Heeran Paul
License: MIT
--------------------------------------------
"""


import secrets
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from security.authentication.authentication_manager import AuthenticationManager
from security.authorization.authorization_manager import AuthorizationManager
from security.encryption.encryption_manager import EncryptionManager
from security.privacy.privacy_manager import PrivacyManager
from security.auditing.audit_manager import AuditManager
from security.sandbox.sandbox_manager import SandboxManager
from security.secrets.secrets_manager import SecretsManager


class SecurityManager:

    """
    ==========================================
           HERCULE SECURITY MANAGER
    ==========================================
    """

    def __init__(self):

        self.authentication = AuthenticationManager()

        self.authorization = AuthorizationManager()

        self.encryption = EncryptionManager()

        self.privacy = PrivacyManager()

        self.audit = AuditManager()

        self.sandbox = SandboxManager()

        self.secrets = SecretsManager()

        self.roles = {}

    ##################################################
    # USERS
    ##################################################

    def register_user(
        self,
        username,
        password,
    ):
        hashed = self.encryption.hash(password)
        self.authentication.register(username, hashed)
        self.audit.log(f"Registered user {username}")

    ##################################################

    def login(self, username, password):
        hashed = self.encryption.hash(password)
        authenticated = self.authentication.authenticate(username, hashed)
        if not authenticated:
            return None
        token = secrets.token_hex(32)
        self.authentication.create_session(username, token)
        self.audit.log(f"{username} logged in")
        return token

    ##################################################

    def logout(self, token):
        self.authentication.remove_session(token)

    ##################################################
    # ROLES
    ##################################################

    def assign_role(self, username, role):
        self.roles[username] = role

    ##################################################

    def role(self, username):
        return self.roles.get(username)

    ##################################################
    # PERMISSIONS
    ##################################################

    def grant(self, username, permission):
        self.authorization.grant(username, permission)

    ##################################################

    def revoke(self, username, permission):
        self.authorization.revoke(username, permission)

    ##################################################

    def allowed(self, username, permission):
        return self.authorization.has_permission(username, permission)

    ##################################################
    # API KEYS (stored in encrypted SecretsManager)
    ##################################################

    def create_api_key(
        self,
        owner: str,
        expires_in: Optional[int] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        """Create a new API key and store it securely."""
        key = secrets.token_hex(32)
        key_name = f"api_key_{key[:16]}"
        success = self.secrets.set_secret(
            name=key_name,
            value=key,
            owner=owner,
            expires_in=expires_in,
            tags=(tags or []) + ["api_key"],
            metadata={"type": "api_key", "prefix": key[:8]},
        )
        if success:
            self.audit.log(f"Created API key for {owner}")
            return key
        raise RuntimeError("Failed to store API key")

    def validate_api_key(self, key: str) -> Optional[Dict[str, Any]]:
        """Validate an API key and return metadata."""
        key_name = f"api_key_{key[:16]}"
        stored = self.secrets.get_secret(key_name)
        if stored == key:
            meta = self.secrets.get_secret_metadata(key_name)
            return {"valid": True, "owner": meta.get("owner") if meta else "unknown", "metadata": meta}
        return None

    def revoke_api_key(self, key: str) -> bool:
        """Revoke an API key."""
        key_name = f"api_key_{key[:16]}"
        success = self.secrets.delete_secret(key_name)
        if success:
            self.audit.log(f"Revoked API key {key[:8]}")
        return success

    def list_api_keys(self, owner: Optional[str] = None) -> List[Dict[str, Any]]:
        """List API keys (metadata only)."""
        all_secrets = self.secrets.list_secrets(tags=["api_key"])
        if owner:
            all_secrets = [s for s in all_secrets if s.get("owner") == owner]
        return all_secrets

    ##################################################
    # PRIVACY
    ##################################################

    def enable_private_mode(self):
        self.privacy.enable()

    ##################################################

    def disable_private_mode(self):
        self.privacy.disable()

    ##################################################
    # SANDBOX
    ##################################################

    def enable_sandbox(self):
        self.sandbox.enable()

    ##################################################

    def disable_sandbox(self):
        self.sandbox.disable()

    ##################################################
    # AUDIT
    ##################################################

    def audit_log(self, message):
        self.audit.log(message)

    ##################################################

    def audit_history(self):
        return self.audit.history()

    ##################################################
    # HEALTH
    ##################################################

    def health(self):
        return {
            "authentication": True,
            "authorization": True,
            "encryption": True,
            "privacy": self.privacy.status(),
            "sandbox": self.sandbox.status(),
            "secrets": self.secrets.get_stats() if hasattr(self.secrets, "get_stats") else {"status": "active"},
            "audit_logs": len(self.audit.history()),
        }

    ##################################################
    # FUTURE
    ##################################################

    def biometric_login(self):
        pass

    ##################################################

    def face_unlock(self):
        pass

    ##################################################

    def voice_unlock(self):
        pass

    ##################################################

    def hardware_security_module(self):
        pass

    ##################################################

    def secure_boot(self):
        pass

    ##################################################

    def zero_trust_validation(self):
        pass

    ##################################################

    def intrusion_detection(self):
        pass

    ##################################################

    def threat_analysis(self):
        pass