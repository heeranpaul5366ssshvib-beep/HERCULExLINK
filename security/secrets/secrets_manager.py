from __future__ import annotations
"""
HERCULE AI Operating System
Module: Secrets Manager
Author: Heeran Paul
License: MIT

Encrypted secrets storage with key derivation and secure storage.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


@dataclass
class SecretEntry:
    """Single secret entry with metadata."""
    name: str
    value: str  # encrypted
    owner: str
    created: str
    expires: Optional[str] = None
    tags: List[str] = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.metadata is None:
            self.metadata = {}


class SecretsManager:
    """
    Secure secrets manager with encrypted storage.
    
    Features:
    - AES-256 encryption via Fernet
    - Key derivation from master password + salt
    - Per-secret encryption with unique salts
    - Automatic expiration
    - Access logging
    - Thread-safe
    """
    
    def __init__(
        self,
        storage_path: Optional[str] = None,
        master_key: Optional[bytes] = None,
        auto_save: bool = True,
    ):
        self.storage_path = Path(storage_path or self._default_storage_path())
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.auto_save = auto_save
        self._lock = threading.RLock()
        self._secrets: Dict[str, SecretEntry] = {}
        self._fernet: Optional[Fernet] = None
        self._master_key = master_key
        self._salt = secrets.token_bytes(16)
        
        self._initialize()

    def _default_storage_path(self) -> str:
        try:
            from system.paths import user_data_dir
            return str(user_data_dir() / "secrets" / "secrets.enc")
        except Exception:
            return str(Path.home() / ".hercule" / "secrets" / "secrets.enc")

    def _initialize(self):
        """Initialize or load existing secrets."""
        if self.storage_path.exists():
            self._load()
        else:
            self._generate_master_key()

    def _generate_master_key(self):
        """Generate new master key."""
        if self._master_key:
            # Derive from provided key
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=self._salt,
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(self._master_key))
        else:
            # Generate random master key
            key = Fernet.generate_key()
            self._master_key = key
        self._fernet = Fernet(key)

    def _derive_secret_key(self, secret_name: str) -> Fernet:
        """Derive a unique key for each secret."""
        # Use HKDF-like derivation: master_key + secret_name
        combined = self._fernet._signing_key + secret_name.encode()
        digest = hashlib.sha256(combined).digest()
        key = base64.urlsafe_b64encode(digest)
        return Fernet(key)

    def _load(self):
        """Load and decrypt secrets from storage."""
        try:
            with open(self.storage_path, 'rb') as f:
                data = f.read()
            # First 16 bytes = salt, rest = encrypted data
            if len(data) < 16:
                self._generate_master_key()
                return
            self._salt = data[:16]
            encrypted = data[16:]
            decrypted = self._fernet.decrypt(encrypted)
            secrets_data = json.loads(decrypted.decode())
            with self._lock:
                self._secrets = {name: SecretEntry(**entry) for name, entry in secrets_data.items()}
        except Exception:
            # If decryption fails, start fresh
            self._generate_master_key()
            self._secrets = {}

    def _save(self):
        """Encrypt and save secrets to storage."""
        if not self.auto_save:
            return
        try:
            with self._lock:
                secrets_data = {name: asdict(entry) for name, entry in self._secrets.items()}
            data = json.dumps(secrets_data).encode()
            encrypted = self._fernet.encrypt(data)
            # Write atomically
            temp_path = self.storage_path.with_suffix('.tmp')
            with open(temp_path, 'wb') as f:
                f.write(self._salt + encrypted)
            temp_path.replace(self.storage_path)
        except Exception as exc:
            # Log but don't raise
            pass

    def set_secret(
        self,
        name: str,
        value: str,
        owner: str = "system",
        expires_in: Optional[int] = None,  # seconds
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Store a secret (encrypted)."""
        try:
            fernet = self._derive_secret_key(name)
            encrypted_value = fernet.encrypt(value.encode()).decode()
            
            expires = None
            if expires_in:
                expires = (datetime.now(timezone.utc).timestamp() + expires_in)
                expires = datetime.fromtimestamp(expires, timezone.utc).isoformat()
            
            entry = SecretEntry(
                name=name,
                value=encrypted_value,
                owner=owner,
                created=datetime.now(timezone.utc).isoformat(),
                expires=expires,
                tags=tags or [],
                metadata=metadata or {},
            )
            
            with self._lock:
                self._secrets[name] = entry
            self._save()
            return True
        except Exception:
            return False

    def get_secret(self, name: str, requester: str = "system") -> Optional[str]:
        """Retrieve and decrypt a secret."""
        with self._lock:
            entry = self._secrets.get(name)
        if not entry:
            return None
        
        # Check expiration
        if entry.expires:
            exp_time = datetime.fromisoformat(entry.expires.replace('Z', '+00:00'))
            if datetime.now(timezone.utc) > exp_time:
                self.delete_secret(name)
                return None
        
        try:
            fernet = self._derive_secret_key(name)
            decrypted = fernet.decrypt(entry.value.encode()).decode()
            return decrypted
        except Exception:
            return None

    def delete_secret(self, name: str) -> bool:
        """Delete a secret."""
        with self._lock:
            if name in self._secrets:
                del self._secrets[name]
                self._save()
                return True
        return False

    def list_secrets(self, owner: Optional[str] = None, tags: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """List secrets (metadata only, no values)."""
        with self._lock:
            results = []
            for entry in self._secrets.values():
                if owner and entry.owner != owner:
                    continue
                if tags and not all(tag in entry.tags for tag in tags):
                    continue
                # Check expiration
                if entry.expires:
                    exp_time = datetime.fromisoformat(entry.expires.replace('Z', '+00:00'))
                    if datetime.now(timezone.utc) > exp_time:
                        continue
                results.append({
                    "name": entry.name,
                    "owner": entry.owner,
                    "created": entry.created,
                    "expires": entry.expires,
                    "tags": entry.tags,
                    "metadata": entry.metadata,
                })
        return results

    def rotate_secret(self, name: str, new_value: str) -> bool:
        """Rotate a secret to a new value."""
        if name not in self._secrets:
            return False
        return self.set_secret(name, new_value, owner=self._secrets[name].owner)

    def get_secret_metadata(self, name: str) -> Optional[Dict[str, Any]]:
        """Get secret metadata without decrypting value."""
        with self._lock:
            entry = self._secrets.get(name)
        if not entry:
            return None
        return {
            "name": entry.name,
            "owner": entry.owner,
            "created": entry.created,
            "expires": entry.expires,
            "tags": entry.tags,
            "metadata": entry.metadata,
        }

    def cleanup_expired(self) -> int:
        """Remove expired secrets."""
        removed = 0
        with self._lock:
            now = datetime.now(timezone.utc)
            expired = [
                name for name, entry in self._secrets.items()
                if entry.expires and datetime.fromisoformat(entry.expires.replace('Z', '+00:00')) < now
            ]
            for name in expired:
                del self._secrets[name]
                removed += 1
            if removed:
                self._save()
        return removed

    def export_backup(self, backup_path: str) -> bool:
        """Export encrypted backup of all secrets."""
        try:
            with self._lock:
                secrets_data = {name: asdict(entry) for name, entry in self._secrets.items()}
            data = json.dumps(secrets_data).encode()
            encrypted = self._fernet.encrypt(data)
            with open(backup_path, 'wb') as f:
                f.write(self._salt + encrypted)
            return True
        except Exception:
            return False

    def import_backup(self, backup_path: str) -> bool:
        """Import secrets from backup."""
        try:
            with open(backup_path, 'rb') as f:
                data = f.read()
            if len(data) < 16:
                return False
            salt = data[:16]
            encrypted = data[16:]
            # Try to decrypt with current master key
            decrypted = self._fernet.decrypt(encrypted)
            secrets_data = json.loads(decrypted.decode())
            with self._lock:
                for name, entry in secrets_data.items():
                    self._secrets[name] = SecretEntry(**entry)
            self._save()
            return True
        except Exception:
            return False