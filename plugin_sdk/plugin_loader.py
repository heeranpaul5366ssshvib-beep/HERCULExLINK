from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Plugin Loader - Discovery, Validation, Installation
--------------------------------------------
"""

import importlib
import importlib.util
import json
import logging
import os
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from plugin_sdk.plugin import Plugin, PluginStatus
from plugin_sdk.manifest import PluginManifest, PluginPermission, PluginCapability
from plugin_sdk.permissions import PluginPermissionModel
from plugin_sdk.signature import SignatureVerifier, VerificationResult


logger = logging.getLogger("HERCULE.PluginLoader")


class PluginValidationError(Exception):
    """Raised when plugin validation fails."""
    pass


class PluginLoadError(Exception):
    """Raised when plugin loading fails."""
    pass


class PluginLoader:
    """
    Handles plugin discovery, validation, and loading.
    Supports local plugin packages and directories.
    """

    def __init__(
        self,
        plugins_dir: Path = Path("plugins"),
        installed_dir: Path = Path("data/plugins/installed"),
        permission_model: Optional[PluginPermissionModel] = None,
    ):
        self.plugins_dir = plugins_dir
        self.installed_dir = installed_dir
        self.permission_model = permission_model
        self.installed_dir.mkdir(parents=True, exist_ok=True)

    # ============================================================
    # DISCOVERY
    # ============================================================

    def discover(self, folder: Optional[str] = None) -> List[Dict[str, Any]]:
        """Discover available plugins in a folder."""
        search_path = Path(folder) if folder else self.plugins_dir
        if not search_path.exists():
            return []

        plugins = []
        for item in search_path.iterdir():
            if item.name.startswith("_"):
                continue

            if item.is_dir():
                # Directory-based plugin
                manifest_path = item / "manifest.json"
                if manifest_path.exists():
                    plugins.append(self._load_manifest_info(manifest_path, item))
            elif item.suffix == ".zip":
                # Packaged plugin
                plugins.append(self._load_packaged_info(item))

        return plugins

    def _load_manifest_info(self, manifest_path: Path, plugin_dir: Path) -> Dict[str, Any]:
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest_data = json.load(f)
            
            # Verify signature if present
            sig_result = SignatureVerifier().verify_manifest(manifest_data)
            if not sig_result.valid:
                return {
                    "manifest": None,
                    "source_path": plugin_dir,
                    "type": "directory",
                    "valid": False,
                    "errors": [f"Signature verification failed: {sig_result.error}"],
                    "signature_result": {"valid": False, "error": sig_result.error},
                }
            
            manifest = PluginManifest.from_dict(manifest_data)
            return {
                "manifest": manifest,
                "source_path": plugin_dir,
                "type": "directory",
                "valid": True,
                "errors": [],
                "signature_result": {"valid": True, "signer": "trusted"},
            }
        except Exception as e:
            return {
                "manifest": None,
                "source_path": plugin_dir,
                "type": "directory",
                "valid": False,
                "errors": [str(e)],
                "signature_result": {"valid": False, "error": str(e)},
            }

    def _load_packaged_info(self, package_path: Path) -> Dict[str, Any]:
        try:
            with zipfile.ZipFile(package_path, "r") as zf:
                if "manifest.json" not in zf.namelist():
                    raise PluginValidationError("manifest.json not found in package")
                with zf.open("manifest.json") as f:
                    manifest_data = json.load(f)
            
            # Verify signature if present
            sig_result = SignatureVerifier().verify_manifest(manifest_data)
            if not sig_result.valid:
                return {
                    "manifest": None,
                    "source_path": package_path,
                    "type": "package",
                    "valid": False,
                    "errors": [f"Signature verification failed: {sig_result.error}"],
                    "signature_result": {"valid": False, "error": sig_result.error},
                }
            
            manifest = PluginManifest.from_dict(manifest_data)
            return {
                "manifest": manifest,
                "source_path": package_path,
                "type": "package",
                "valid": True,
                "errors": [],
                "signature_result": {"valid": True, "signer": "trusted"},
            }
        except Exception as e:
            return {
                "manifest": None,
                "source_path": package_path,
                "type": "package",
                "valid": False,
                "errors": [str(e)],
                "signature_result": {"valid": False, "error": str(e)},
            }

    # ============================================================
    # VALIDATION
    # ============================================================

    def validate(self, manifest: PluginManifest, hercule_version: str = "1.0.0") -> Tuple[bool, List[str]]:
        """Validate a plugin manifest and return (is_valid, errors)."""
        errors = []

        # Basic manifest validation
        errors.extend(manifest.validate())

        # Signature verification
        manifest_dict = manifest.to_dict()
        sig_result = SignatureVerifier().verify_manifest(manifest_dict)
        if not sig_result.valid:
            errors.append(f"Signature verification failed: {sig_result.error}")

        # Version compatibility check
        if not self._check_version_compatibility(manifest, hercule_version):
            errors.append(f"Incompatible HERCULE version: requires {manifest.min_hercule_version}, current {hercule_version}")

        # Entrypoint validation
        if not manifest.entrypoint:
            errors.append("entrypoint is required")

        return len(errors) == 0, errors

    def _check_version_compatibility(self, manifest: PluginManifest, hercule_version: str) -> bool:
        """Check if plugin is compatible with current HERCULE version."""
        try:
            from packaging import version
            hercule_ver = version.parse(hercule_version)
            min_ver = version.parse(manifest.min_hercule_version)
            if hercule_ver < min_ver:
                return False
            if manifest.max_hercule_version:
                max_ver = version.parse(manifest.max_hercule_version)
                if hercule_ver > max_ver:
                    return False
            return True
        except Exception:
            # If version parsing fails, allow it (lenient)
            return True

    # ============================================================
    # INSTALLATION
    # ============================================================

    def install(
        self,
        source_path: Path,
        plugin_id: str,
        force: bool = False,
    ) -> Tuple[bool, str]:
        """
        Install a plugin from source path.
        Returns (success, message).
        """
        # Determine if directory or package
        if source_path.is_dir():
            return self._install_from_directory(source_path, plugin_id, force)
        elif source_path.suffix == ".zip":
            return self._install_from_package(source_path, plugin_id, force)
        else:
            return False, f"Invalid source: {source_path}"

    def _install_from_directory(self, source_dir: Path, plugin_id: str, force: bool) -> Tuple[bool, str]:
        target_dir = self.installed_dir / plugin_id

        if target_dir.exists():
            if not force:
                return False, f"Plugin {plugin_id} already installed. Use force=True to overwrite."
            shutil.rmtree(target_dir)

        try:
            shutil.copytree(source_dir, target_dir)
            logger.info(f"Installed plugin {plugin_id} from {source_dir}")
            return True, f"Plugin {plugin_id} installed successfully"
        except Exception as e:
            logger.error(f"Failed to install plugin {plugin_id}: {e}")
            return False, f"Installation failed: {e}"

    def _install_from_package(self, package_path: Path, plugin_id: str, force: bool) -> Tuple[bool, str]:
        target_dir = self.installed_dir / plugin_id

        if target_dir.exists():
            if not force:
                return False, f"Plugin {plugin_id} already installed. Use force=True to overwrite."
            shutil.rmtree(target_dir)

        try:
            with zipfile.ZipFile(package_path, "r") as zf:
                # Validate all paths before extraction to prevent path traversal
                target_abs = target_dir.resolve()
                # Ensure target_abs ends with separator for strict prefix check
                target_abs_str = str(target_abs)
                if not target_abs_str.endswith(os.sep):
                    target_abs_str += os.sep
                
                for member in zf.namelist():
                    # Check for absolute paths
                    if os.path.isabs(member):
                        raise zipfile.BadZipFile(f"Absolute path in archive: {member}")
                    # Check for path traversal
                    member_path = (target_dir / member).resolve()
                    member_path_str = str(member_path)
                    # Strict prefix check: must be within target_dir (with separator)
                    if not member_path_str.startswith(target_abs_str):
                        raise zipfile.BadZipFile(f"Path traversal attempt: {member}")
                    # Check for drive letters (Windows)
                    if ':' in member and member[1:3] in (':\\', ':/'):
                        raise zipfile.BadZipFile(f"Drive letter in path: {member}")
                
                # All paths validated, safe to extract
                zf.extractall(target_dir)
            logger.info(f"Installed plugin {plugin_id} from package {package_path}")
            return True, f"Plugin {plugin_id} installed successfully"
        except zipfile.BadZipFile as e:
            logger.error(f"Invalid plugin package {package_path}: {e}")
            # Clean up partial extraction
            if target_dir.exists():
                shutil.rmtree(target_dir, ignore_errors=True)
            return False, f"Invalid package: {e}"
        except Exception as e:
            logger.error(f"Failed to install plugin {plugin_id} from package: {e}")
            if target_dir.exists():
                shutil.rmtree(target_dir, ignore_errors=True)
            return False, f"Installation failed: {e}"

    # ============================================================
    # LOADING
    # ============================================================

    def load_plugin(self, plugin_id: str, hercule_version: str = "1.0.0") -> Tuple[Optional[Plugin], PluginManifest, List[str]]:
        """
        Load and instantiate a plugin.
        Returns (plugin_instance, manifest, errors).
        """
        plugin_dir = self.installed_dir / plugin_id
        if not plugin_dir.exists():
            return None, None, [f"Plugin {plugin_id} not installed"]

        manifest_path = plugin_dir / "manifest.json"
        if not manifest_path.exists():
            return None, None, [f"manifest.json not found for {plugin_id}"]

        # Load and validate manifest
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest_data = json.load(f)
            manifest = PluginManifest.from_dict(manifest_data)
        except Exception as e:
            return None, None, [f"Failed to load manifest: {e}"]

        # Validate
        valid, errors = self.validate(manifest, hercule_version)
        if not valid:
            return None, manifest, errors

        # Load plugin module
        try:
            plugin = self._load_plugin_module(plugin_dir, manifest)
            if plugin:
                plugin.set_manifest(manifest)
                plugin._set_status(PluginStatus.VALIDATED)
            return plugin, manifest, []
        except Exception as e:
            logger.error(f"Failed to load plugin {plugin_id}: {e}")
            return None, manifest, [f"Failed to load plugin module: {e}"]

    def _load_plugin_module(self, plugin_dir: Path, manifest: PluginManifest) -> Plugin:
        """Load the plugin class from the entrypoint."""
        # Use importlib.util to load module from specific file path, avoiding sys.modules cache
        entrypoint = manifest.entrypoint
        if entrypoint.endswith(".py"):
            entrypoint_file = entrypoint
        else:
            entrypoint_file = entrypoint + ".py"
        
        entrypoint_path = plugin_dir / entrypoint_file
        if not entrypoint_path.exists():
            raise PluginLoadError(f"Entrypoint file not found: {entrypoint_path}")
        
        # Create a unique module name to avoid conflicts
        unique_module_name = f"hercule_plugin_{manifest.plugin_id.replace('.', '_')}"
        
        # Load module from specific file path
        spec = importlib.util.spec_from_file_location(unique_module_name, entrypoint_path)
        if spec is None or spec.loader is None:
            raise PluginLoadError(f"Could not load module from {entrypoint_path}")
        
        module = importlib.util.module_from_spec(spec)
        sys.modules[unique_module_name] = module
        spec.loader.exec_module(module)
        
        # Find the Plugin class
        plugin_class = None
        for name in dir(module):
            obj = getattr(module, name)
            if isinstance(obj, type) and issubclass(obj, Plugin) and obj is not Plugin:
                plugin_class = obj
                break

        if not plugin_class:
            raise PluginLoadError(f"No Plugin subclass found in {entrypoint_path}")

        # Instantiate
        return plugin_class()

    # ============================================================
    # UNINSTALL
    # ============================================================

    def uninstall(self, plugin_id: str) -> Tuple[bool, str]:
        """Uninstall a plugin."""
        plugin_dir = self.installed_dir / plugin_id
        if not plugin_dir.exists():
            return False, f"Plugin {plugin_id} not installed"

        try:
            shutil.rmtree(plugin_dir)
            logger.info(f"Uninstalled plugin {plugin_id}")
            return True, f"Plugin {plugin_id} uninstalled successfully"
        except Exception as e:
            logger.error(f"Failed to uninstall plugin {plugin_id}: {e}")
            return False, f"Uninstall failed: {e}"

    # ============================================================
    # HELPER
    # ============================================================

    def get_installed_plugins(self) -> List[str]:
        """Get list of installed plugin IDs."""
        return [d.name for d in self.installed_dir.iterdir() if d.is_dir()]

    def get_plugin_path(self, plugin_id: str) -> Optional[Path]:
        """Get the installation path for a plugin."""
        path = self.installed_dir / plugin_id
        return path if path.exists() else None