from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Plugin Manifest Schema
--------------------------------------------
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum


class PluginPermission(str, Enum):
    """Explicit plugin permissions - independent capabilities."""
    FILESYSTEM_READ = "filesystem_read"
    FILESYSTEM_WRITE = "filesystem_write"
    NETWORK = "network"
    PROCESS_EXECUTION = "process_execution"
    SHELL = "shell"
    MICROPHONE = "microphone"
    CAMERA = "camera"
    SYSTEM_INFO = "system_info"
    SECRETS = "secrets"
    BROWSER = "browser"
    CLIPBOARD = "clipboard"
    AUTOMATION = "automation"


class PluginCapability(str, Enum):
    """Plugin capabilities - what the plugin can do."""
    SEARCH = "search"
    RESEARCH = "research"
    SUMMARIZE = "summarize"
    CODE_GENERATION = "code_generation"
    FILE_OPERATIONS = "file_operations"
    TERMINAL = "terminal"
    BROWSER_AUTOMATION = "browser_automation"
    DATA_ANALYSIS = "data_analysis"
    IMAGE_PROCESSING = "image_processing"
    AUDIO_PROCESSING = "audio_processing"
    CALCULATOR = "calculator"
    SYSTEM_INFO = "system_info"
    TIME_UTILITY = "time_utility"
    NETWORK_REQUEST = "network_request"
    HTTP_CLIENT = "http_client"
    AUTOMATION = "automation"
    CLIPBOARD = "clipboard"
    CUSTOM = "custom"


class PluginStatus(str, Enum):
    """Plugin lifecycle status."""
    DISCOVERED = "discovered"
    VALIDATED = "validated"
    INSTALLED = "installed"
    DISABLED = "disabled"
    ENABLED = "enabled"
    RUNNING = "running"
    INVALID = "invalid"
    INCOMPATIBLE = "incompatible"
    FAILED = "failed"
    PERMISSION_DENIED = "permission_denied"


@dataclass
class PluginManifest:
    """Complete plugin manifest with all metadata."""

    plugin_id: str
    name: str
    version: str
    description: str = ""
    author: str = "Unknown"
    homepage: Optional[str] = None
    min_hercule_version: str = "1.0.0"
    max_hercule_version: Optional[str] = None
    entrypoint: str = "Plugin"
    capabilities: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    configuration_schema: Dict[str, Any] = field(default_factory=dict)
    plugin_api_version: str = "1.0"
    icon: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    # Supply chain verification
    signature: Optional[str] = None  # base64 encoded signature
    signature_algorithm: str = "ed25519"
    public_key: Optional[str] = None  # base64 encoded public key
    signed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plugin_id": self.plugin_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "homepage": self.homepage,
            "min_hercule_version": self.min_hercule_version,
            "max_hercule_version": self.max_hercule_version,
            "entrypoint": self.entrypoint,
            "capabilities": self.capabilities,
            "permissions": self.permissions,
            "dependencies": self.dependencies,
            "configuration_schema": self.configuration_schema,
            "plugin_api_version": self.plugin_api_version,
            "icon": self.icon,
            "tags": self.tags,
            "signature": self.signature,
            "signature_algorithm": self.signature_algorithm,
            "public_key": self.public_key,
            "signed_at": self.signed_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PluginManifest":
        return cls(
            plugin_id=data.get("plugin_id", ""),
            name=data.get("name", ""),
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            author=data.get("author", "Unknown"),
            homepage=data.get("homepage"),
            min_hercule_version=data.get("min_hercule_version", "1.0.0"),
            max_hercule_version=data.get("max_hercule_version"),
            entrypoint=data.get("entrypoint", "Plugin"),
            capabilities=data.get("capabilities", []),
            permissions=data.get("permissions", []),
            dependencies=data.get("dependencies", []),
            configuration_schema=data.get("configuration_schema", {}),
            plugin_api_version=data.get("plugin_api_version", "1.0"),
            icon=data.get("icon"),
            tags=data.get("tags", []),
            signature=data.get("signature"),
            signature_algorithm=data.get("signature_algorithm", "ed25519"),
            public_key=data.get("public_key"),
            signed_at=data.get("signed_at"),
        )

    def validate(self) -> List[str]:
        """Validate manifest and return list of errors (empty if valid)."""
        errors = []
        if not self.plugin_id:
            errors.append("plugin_id is required")
        if not self.name:
            errors.append("name is required")
        if not self.version:
            errors.append("version is required")
        if not self.entrypoint:
            errors.append("entrypoint is required")
        for perm in self.permissions:
            if perm not in [p.value for p in PluginPermission]:
                errors.append(f"unknown permission: {perm}")
        for cap in self.capabilities:
            if cap not in [c.value for c in PluginCapability] and cap != "custom":
                errors.append(f"unknown capability: {cap}")
        return errors