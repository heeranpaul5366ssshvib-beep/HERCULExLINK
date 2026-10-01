"""
Repair Engine Configuration
"""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RepairConfig:
    """
    Global Smart Repair configuration.
    """

    # Root directory of HERCULE
    project_root: Path = Path.cwd()

    # Backup settings
    backup_enabled: bool = True
    backup_directory: str = "developer_tools/smart_repair/backups"

    # Validation
    validate_after_patch: bool = True
    rollback_on_failure: bool = True

    # Safety
    preserve_comments: bool = True
    preserve_formatting: bool = True
    preserve_docstrings: bool = True

    # Repair Strategy
    compatibility_mode: bool = True
    minimal_changes: bool = True
    create_wrappers: bool = True

    # Analysis
    analyze_dependencies: bool = True
    analyze_interfaces: bool = True
    analyze_imports: bool = True
    analyze_runtime: bool = True

    # Logging
    verbose: bool = True
    save_reports: bool = True

    # File Types
    supported_extensions: tuple = field(
        default_factory=lambda: (
            ".py",
        )
    )

    # Ignore folders
    ignored_directories: tuple = field(
        default_factory=lambda: (
            "__pycache__",
            ".git",
            ".idea",
            ".vscode",
            "venv",
            ".venv",
            "build",
            "dist",
        )
    )

    def backup_path(self) -> Path:
        """
        Returns backup folder.

        Frozen (installed) apps must never write into Program Files:
        dev-tool backups redirect into %LOCALAPPDATA%\\HERCULE.
        """
        try:
            from system.paths import is_frozen, user_data_dir
            if is_frozen():
                return user_data_dir() / "smart_repair_backups"
        except Exception:
            pass
        return self.project_root / self.backup_directory

    def is_supported(self, path: Path) -> bool:
        """
        Checks whether a file is supported.
        """
        return path.suffix in self.supported_extensions