from __future__ import annotations
"""
HERCULE Configuration Management
Author: Heeran Paul
License: MIT

Centralized configuration with Pydantic Settings:
- Validation and type safety
- Environment variable support
- YAML/JSON config files
- Secrets management integration
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import yaml


class ModelConfig(BaseModel):
    """Model inference configuration."""
    provider: str = Field(default="builtin", description="Model provider: builtin, ollama, hercule-lm, mock")
    default_model: str = Field(default="", description="Default model ID")
    ollama_host: str = Field(default="http://localhost:11434", description="Ollama server URL")
    ollama_timeout_s: float = Field(default=60.0, ge=1.0, le=600.0)
    allow_mock_fallback: bool = Field(default=False, description="Allow mock adapter as fallback (dev only)")
    model_path: Optional[str] = Field(default=None, description="Path to GGUF model file")
    native_model_path: Optional[str] = Field(default=None, description="Path to HERCULE-LM checkpoint")
    native_tokenizer_dir: Optional[str] = Field(default=None, description="Path to tokenizer directory")
    offline: bool = Field(default=False, description="Disable network access (force builtin)")


class SecurityConfig(BaseModel):
    """Security and sandbox configuration."""
    sandbox_enabled: bool = Field(default=True)
    sandbox_profile: str = Field(default="strict", description="strict, network, filesystem, full")
    audit_log_dir: Optional[str] = Field(default=None, description="Audit log directory")
    audit_max_file_mb: int = Field(default=100, ge=1, le=1000)
    audit_max_files: int = Field(default=10, ge=1, le=100)
    secrets_storage_path: Optional[str] = Field(default=None, description="Encrypted secrets storage")
    rate_limit_enabled: bool = Field(default=True)
    default_rate_limit: int = Field(default=100, description="Requests per minute per ability")
    quota_enabled: bool = Field(default=True)


class SandboxConfig(BaseModel):
    """Sandbox resource limits."""
    profile: str = Field(default="strict", description="strict, network, filesystem, full")
    max_cpu_seconds: float = Field(default=300.0, ge=1.0, le=3600.0)
    max_memory_mb: int = Field(default=1024, ge=64, le=8192)
    max_disk_mb: int = Field(default=500, ge=10, le=10000)
    max_network_mb: int = Field(default=100, ge=0, le=10000)
    max_wall_seconds: float = Field(default=600.0, ge=10.0, le=7200.0)
    max_processes: int = Field(default=10, ge=1, le=100)
    allowed_paths: List[str] = Field(default_factory=list)
    denied_paths: List[str] = Field(default_factory=list)


class AbilitiesConfig(BaseModel):
    """Abilities configuration."""
    enabled_abilities: List[str] = Field(default_factory=list, description="Empty = all")
    disabled_abilities: List[str] = Field(default_factory=list)
    default_timeouts: Dict[str, int] = Field(default_factory=dict)
    custom_abilities: Dict[str, Dict[str, Any]] = Field(default_factory=dict)


class LoggingConfig(BaseModel):
    """Logging configuration."""
    level: str = Field(default="INFO", description="DEBUG, INFO, WARNING, ERROR")
    format: str = Field(default="json", description="json or text")
    file_path: Optional[str] = Field(default=None)
    max_file_mb: int = Field(default=100)
    max_files: int = Field(default=10)
    include_timestamps: bool = Field(default=True)


class MetricsConfig(BaseModel):
    """Metrics and monitoring configuration."""
    enabled: bool = Field(default=True)
    prometheus_enabled: bool = Field(default=True)
    otel_enabled: bool = Field(default=False)
    otel_endpoint: Optional[str] = Field(default=None)
    export_interval_s: int = Field(default=60, ge=10, le=3600)
    retention_days: int = Field(default=7, ge=1, le=90)


class StorageConfig(BaseModel):
    """Storage paths configuration."""
    data_dir: str = Field(default="", description="Base data directory (empty = auto)")
    memory_dir: str = Field(default="", description="Memory persistence directory")
    models_dir: str = Field(default="", description="Models directory")
    cache_dir: str = Field(default="", description="Cache directory")
    temp_dir: str = Field(default="", description="Temporary files directory")


class RuntimeConfig(BaseModel):
    """Runtime configuration."""
    max_concurrent_tasks: int = Field(default=10, ge=1, le=100)
    task_timeout_s: float = Field(default=300.0, ge=10.0, le=3600.0)
    enable_autonomous: bool = Field(default=True)
    enable_plugins: bool = Field(default=False)
    plugin_dirs: List[str] = Field(default_factory=lambda: ["plugins"])


class HERCULESettings(BaseSettings):
    """
    Main HERCULE configuration.
    
    Priority order (highest to lowest):
    1. Environment variables (HERCULE_*)
    2. .env file
    3. Config file (YAML/JSON)
    4. Defaults
    """
    
    # App info
    app_name: str = "HERCULE"
    version: str = "2.0.0"
    environment: str = Field(default="development", description="development, staging, production")
    debug: bool = Field(default=False)
    
    # Sub-configs
    models: ModelConfig = Field(default_factory=ModelConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    abilities: AbilitiesConfig = Field(default_factory=AbilitiesConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    
    model_config = SettingsConfigDict(
        env_prefix="HERCULE_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        validate_default=True,
    )
    
    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        allowed = {"development", "staging", "production", "test"}
        if v not in allowed:
            raise ValueError(f"environment must be one of {allowed}")
        return v
    
    @field_validator("logging")
    @classmethod
    def validate_logging(cls, v: LoggingConfig) -> LoggingConfig:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.level.upper()
        if v_upper not in allowed:
            raise ValueError(f"log level must be one of {allowed}")
        v.level = v_upper
        return v
    
    @model_validator(mode="after")
    def resolve_paths(self) -> "HERCULESettings":
        """Resolve and create storage paths."""
        if not self.storage.data_dir:
            try:
                from system.paths import user_data_dir
                self.storage.data_dir = str(user_data_dir())
            except Exception:
                self.storage.data_dir = str(Path.home() / ".hercule")
        
        base = Path(self.storage.data_dir).resolve()
        base.mkdir(parents=True, exist_ok=True)
        
        if not self.storage.memory_dir:
            self.storage.memory_dir = str(base / "memory")
        if not self.storage.models_dir:
            self.storage.models_dir = str(base / "models")
        if not self.storage.cache_dir:
            self.storage.cache_dir = str(base / "cache")
        if not self.storage.temp_dir:
            self.storage.temp_dir = str(base / "temp")
        
        for path in [self.storage.memory_dir, self.storage.models_dir, self.storage.cache_dir, self.storage.temp_dir]:
            Path(path).mkdir(parents=True, exist_ok=True)
        
        # Ensure models subdirs
        Path(self.storage.models_dir).joinpath("gguf").mkdir(parents=True, exist_ok=True)
        Path(self.storage.models_dir).joinpath("runtime").mkdir(parents=True, exist_ok=True)
        
        # Update models config with resolved paths
        if not self.models.model_path:
            self.models.model_path = str(Path(self.storage.models_dir) / "gguf")
        if not self.models.native_model_path:
            self.models.native_model_path = str(Path(self.storage.models_dir) / "native")
        
        return self
    
    def to_dict(self) -> Dict[str, Any]:
        """Export settings as dictionary."""
        return self.model_dump()
    
    def to_yaml(self) -> str:
        """Export settings as YAML."""
        return yaml.dump(self.model_dump(), default_flow_style=False, sort_keys=False)
    
    def save(self, path: Union[str, Path]):
        """Save settings to YAML file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_yaml(), encoding="utf-8")


@lru_cache
def get_settings(config_file: Optional[Union[str, Path]] = None) -> HERCULESettings:
    """
    Get cached settings instance.
    
    Args:
        config_file: Optional path to YAML/JSON config file
        
    Returns:
        HERCULESettings instance (cached)
    """
    if config_file:
        path = Path(config_file)
        if path.exists():
            if path.suffix in (".yaml", ".yml"):
                with open(path, "r") as f:
                    data = yaml.safe_load(f)
                return HERCULESettings(**data)
            elif path.suffix == ".json":
                import json
                with open(path, "r") as f:
                    data = json.load(f)
                return HERCULESettings(**data)
    return HERCULESettings()


def load_config(config_file: Optional[Union[str, Path]] = None) -> HERCULESettings:
    """Load settings without caching (for config reload)."""
    return get_settings(config_file)


# Backward compatibility with existing runtime_config
def load_runtime_config(overrides: Optional[Dict[str, Any]] = None) -> HERCULESettings:
    """Load runtime config with optional overrides (backward compat)."""
    settings = get_settings()
    if overrides:
        for key, value in overrides.items():
            if hasattr(settings, key):
                setattr(settings, key, value)
    return settings