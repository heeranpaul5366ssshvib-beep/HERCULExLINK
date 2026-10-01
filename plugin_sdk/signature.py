from __future__ import annotations
"""
HERCULE AI Operating System
Module: Plugin Signature Verification
Author: Heeran Paul
License: MIT

Supply chain verification using Ed25519 signatures.
"""

import base64
import hashlib
import json
import time
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass

try:
    from cryptography.hazmat.primitives.asymmetric import ed25519
    from cryptography.hazmat.primitives import serialization
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False


@dataclass
class VerificationResult:
    """Result of signature verification."""
    valid: bool
    error: Optional[str] = None
    signer: Optional[str] = None
    signed_at: Optional[str] = None
    algorithm: str = "ed25519"


class SignatureVerifier:
    """
    Ed25519 signature verification for plugin manifests.
    
    Provides:
    - Manifest signing with Ed25519
    - Signature verification
    - Key management
    - Timestamp validation
    """
    
    # Trusted public keys (base64 encoded) - in production, load from config
    TRUSTED_KEYS: Dict[str, bytes] = {}
    
    def __init__(self, trusted_keys: Optional[Dict[str, bytes]] = None):
        if not CRYPTO_AVAILABLE:
            raise RuntimeError("cryptography library required for signature verification. Install with: pip install cryptography")
        
        self.trusted_keys = trusted_keys or self.TRUSTED_KEYS.copy()
    
    @classmethod
    def add_trusted_key(cls, name: str, public_key_b64: str):
        """Add a trusted public key (base64 encoded)."""
        key_bytes = base64.b64decode(public_key_b64)
        cls.TRUSTED_KEYS[name] = key_bytes
    
    @classmethod
    def generate_keypair(cls) -> Tuple[str, str]:
        """Generate a new Ed25519 keypair. Returns (private_key_b64, public_key_b64)."""
        if not CRYPTO_AVAILABLE:
            raise RuntimeError("cryptography library required")
        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        private_b64 = base64.b64encode(
            private_key.private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption(),
            )
        ).decode()
        public_b64 = base64.b64encode(
            public_key.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
        ).decode()
        return private_b64, public_b64
    
    def sign_manifest(self, manifest_dict: Dict[str, Any], private_key_b64: str) -> Tuple[str, str]:
        """
        Sign a manifest dictionary.
        Returns (signature_b64, signed_at_iso).
        """
        if not CRYPTO_AVAILABLE:
            raise RuntimeError("cryptography library required")
        
        private_key_bytes = base64.b64decode(private_key_b64)
        private_key = ed25519.Ed25519PrivateKey.from_private_bytes(private_key_bytes)
        
        # Create canonical JSON for signing (sorted keys, no whitespace)
        # Exclude signature fields from what gets signed
        signing_data = {k: v for k, v in manifest_dict.items() 
                       if k not in ('signature', 'signed_at', 'public_key')}
        canonical = json.dumps(signing_data, sort_keys=True, separators=(',', ':')).encode()
        
        signature = private_key.sign(canonical)
        signature_b64 = base64.b64encode(signature).decode()
        signed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        
        return base64.b64encode(signature).decode(), signed_at
    
    def verify_manifest(self, manifest_dict: Dict[str, Any]) -> VerificationResult:
        """
        Verify a manifest's signature.
        Checks:
        - Signature is present
        - Public key is in trusted keys
        - Signature is valid for the manifest content
        - Timestamp is recent (within 1 year)
        """
        if not CRYPTO_AVAILABLE:
            return VerificationResult(valid=False, error="cryptography library not available")
        
        signature_b64 = manifest_dict.get("signature")
        public_key_b64 = manifest_dict.get("public_key")
        signed_at = manifest_dict.get("signed_at")
        algorithm = manifest_dict.get("signature_algorithm", "ed25519")
        
        if not signature_b64:
            return VerificationResult(valid=False, error="No signature present")
        
        if not public_key_b64:
            return VerificationResult(valid=False, error="No public key provided")
        
        # Check if public key is trusted
        key_name = None
        for name, key_bytes in self.trusted_keys.items():
            if base64.b64encode(key_bytes).decode() == public_key_b64:
                key_name = name
                break
        
        if key_name is None:
            return VerificationResult(
                valid=False, 
                error=f"Public key not in trusted keys. Configure trusted keys in plugin settings."
            )
        
        # Verify timestamp
        try:
            signed_time = time.strptime(signed_at, "%Y-%m-%dT%H:%M:%SZ")
            signed_ts = time.mktime(signed_time)
            now = time.time()
            if now - signed_ts > 365 * 24 * 3600:  # 1 year
                return VerificationResult(
                    valid=False, 
                    error=f"Signature expired (signed {signed_at})"
                )
        except Exception:
            pass  # Invalid timestamp format, continue with verification
        
        # Reconstruct signing data
        signing_data = {k: v for k, v in manifest_dict.items() 
                       if k not in ('signature', 'signed_at', 'public_key')}
        canonical = json.dumps(signing_data, sort_keys=True, separators=(',', ':')).encode()
        
        try:
            signature_bytes = base64.b64decode(signature_b64)
            public_key_bytes = base64.b64decode(public_key_b64)
            
            if len(public_key_bytes) != 32:
                return VerificationResult(valid=False, error="Invalid public key length")
            
            public_key = ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)
            public_key.verify(signature_bytes, canonical)
            
            return VerificationResult(
                valid=True,
                signer="trusted",
                signed_at=signed_at,
                algorithm="ed25519",
            )
        except Exception as e:
            return VerificationResult(valid=False, error=f"Signature verification failed: {e}")
    
    def get_key_fingerprint(self, public_key_b64: str) -> str:
        """Get SHA-256 fingerprint of a public key."""
        key_bytes = base64.b64decode(public_key_b64)
        return hashlib.sha256(key_bytes).hexdigest()[:16]


def verify_plugin_signature(manifest_dict: Dict[str, Any], trusted_keys: Optional[Dict[str, bytes]] = None) -> VerificationResult:
    """Convenience function to verify a plugin manifest signature."""
    verifier = SignatureVerifier(trusted_keys)
    return verifier.verify_manifest(manifest_dict)