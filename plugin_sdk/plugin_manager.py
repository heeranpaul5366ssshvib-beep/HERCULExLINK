from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Plugin Manager - Full Lifecycle Management
--------------------------------------------
"""

import logging
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from plugin_sdk.plugin import Plugin, PluginStatus, PluginContext
from plugin_sdk.manifest import PluginManifest
from plugin_sdk.permissions import PluginPermissionModel, PluginPermissionChecker
from plugin_sdk.plugin_loader import PluginLoader
from plugin_sdk.plugin_registry import PluginRegistry

logger = logging.getLogger("HERCULE.PluginManager")


class PluginManager:
    """
    Manages the complete lifecycle of plugins:
    DISCOVERED → VALIDATED → INSTALLED → DISABLED → ENABLED → RUNNING
    
    Failure states: INVALID, INCOMPATIBLE, FAILED, DISABLED
    """

    def __init__(
        self,
        plugins_dir: str = "plugins",
        installed_dir: str = "data/plugins/installed",
        config_dir: str = "config/plugins",
        workspace_dir: str = "data/plugins/workspace",
        hercule_version: str = "1.0.0",
        ability_manager: Optional[Any] = None,
        memory_manager: Optional[Any] = None,
        model_router: Optional[Any] = None,
        security_manager: Optional[Any] = None,
        event_bus: Optional[Any] = None,
    ):
        self.hercule_version = hercule_version
        self._permission_model = PluginPermissionModel()
        
        self.loader = PluginLoader(
            plugins_dir=Path(plugins_dir),
            installed_dir=Path(installed_dir),
            permission_model=self._permission_model,
        )
        
        self.registry = PluginRegistry(
            loader=self.loader,
            permission_model=self._permission_model,
            ability_manager=ability_manager,
            memory_manager=memory_manager,
            model_router=model_router,
            security_manager=security_manager,
            event_bus=event_bus,
            workspace_path=workspace_dir,
        )
        
        self._config_dir = Path(config_dir)
        self._config_dir.mkdir(parents=True, exist_ok=True)
        self._workspace_dir = Path(workspace_dir)
        self._workspace_dir.mkdir(parents=True, exist_ok=True)
        
        self._lock = threading.RLock()
        self._contexts: Dict[str, PluginContext] = {}

    # ============================================================
    # DISCOVERY
    # ============================================================

    def discover(self, folder: Optional[str] = None) -> List[Dict[str, Any]]:
        """Discover available plugins."""
        return self.loader.discover(folder)

    # ============================================================
    # VALIDATION
    # ============================================================

    def validate(self, plugin_id: str) -> Tuple[bool, List[str]]:
        """Validate an installed plugin."""
        plugin, manifest, errors = self.loader.load_plugin(plugin_id, self.hercule_version)
        if manifest:
            self.registry._manifests[plugin_id] = manifest
        return len(errors) == 0, errors

    # ============================================================
    # INSTALLATION
    # ============================================================

    def install(
        self,
        source_path: str,
        plugin_id: Optional[str] = None,
        force: bool = False,
    ) -> Tuple[bool, str]:
        """Install a plugin from local package or directory."""
        source = Path(source_path)
        if not source.exists():
            return False, f"Source not found: {source_path}"

        # If plugin_id not provided, try to get from manifest
        manifest_plugin_id = None
        if not plugin_id:
            if source.is_dir():
                manifest_path = source / "manifest.json"
            else:
                # For zip, we'd need to extract manifest first
                return False, "plugin_id required for package installation"
            
            if manifest_path.exists():
                import json
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest_data = json.load(f)
                manifest_plugin_id = manifest_data.get("plugin_id")
                plugin_id = manifest_plugin_id
        
        if not plugin_id:
            return False, "Could not determine plugin_id"

        # If plugin_id was provided, validate it matches manifest
        if manifest_plugin_id is not None and manifest_plugin_id != plugin_id:
            return False, f"Plugin ID mismatch: manifest has '{manifest_plugin_id}', provided '{plugin_id}'"

        # For zip files with provided plugin_id, validate against manifest inside zip
        if not source.is_dir() and source.suffix == ".zip" and plugin_id:
            try:
                import zipfile
                with zipfile.ZipFile(source, "r") as zf:
                    if "manifest.json" in zf.namelist():
                        import json
                        with zf.open("manifest.json") as f:
                            manifest_data = json.load(f)
                        manifest_plugin_id = manifest_data.get("plugin_id")
                        if manifest_plugin_id and manifest_plugin_id != plugin_id:
                            return False, f"Plugin ID mismatch: manifest has '{manifest_plugin_id}', provided '{plugin_id}'"
            except Exception:
                pass  # If we can't read manifest, let loader handle it

        success, msg = self.loader.install(source, plugin_id, force)
        if success:
            # Load and store manifest in registry for permission management
            plugin, manifest, errors = self.loader.load_plugin(plugin_id, self.hercule_version)
            if manifest:
                self.registry._manifests[plugin_id] = manifest
        return success, msg

    # ============================================================
    # ENABLE/DISABLE
    # ============================================================

    def enable(self, plugin_id: str) -> Tuple[bool, str]:
        """Enable a plugin."""
        with self._lock:
            plugin = self.registry.get(plugin_id)
            if not plugin:
                # Try to load it
                plugin, manifest, errors = self.loader.load_plugin(plugin_id, self.hercule_version)
                if not plugin:
                    return False, f"Plugin not found or failed to load: {errors}"
                plugin.set_manifest(manifest)
                self.registry.register(plugin)
                
                # Load config
                config = self.registry.load_config(plugin_id, str(self._config_dir))
                plugin.set_config(config)

            if plugin.status == PluginStatus.ENABLED:
                return True, "Already enabled"

            if plugin.status in (PluginStatus.INVALID, PluginStatus.INCOMPATIBLE, PluginStatus.FAILED):
                return False, f"Cannot enable plugin in state: {plugin.status.value}"

            # Check permissions
            manifest = self.registry.get_manifest(plugin_id)
            if manifest:
                pending_perms = []
                for perm in manifest.permissions:
                    if self._permission_model.is_sensitive(perm):
                        if not self._permission_model.is_granted(plugin_id, manifest.version, perm):
                            pending_perms.append(perm)
                
                if pending_perms:
                    plugin._set_status(PluginStatus.PERMISSION_DENIED)
                    plugin._set_error(f"Missing approvals for sensitive permissions: {pending_perms}")
                    return False, f"Missing approvals for sensitive permissions: {pending_perms}"

            # Create context
            context = self._create_context(plugin, manifest)
            plugin.set_context(context)
            self._contexts[plugin_id] = context

            # Clean up any existing tools for this plugin (in case of re-enable)
            self._unregister_plugin_tools(plugin)

            # Call plugin lifecycle
            try:
                plugin._set_status(PluginStatus.ENABLED)
                success = plugin.on_enable()
                if not success:
                    plugin._enabled = False
                    plugin._set_status(PluginStatus.FAILED)
                    plugin._set_error("on_enable returned False")
                    return False, "Plugin on_enable failed"
                # Ensure enabled flag is set on success
                plugin._enabled = True
            except Exception as e:
                plugin._enabled = False
                plugin._set_status(PluginStatus.FAILED)
                plugin._set_error(str(e))
                logger.error(f"Plugin {plugin_id} enable failed: {e}")
                return False, f"Enable failed: {e}"

            # Register tools/abilities
            self._register_plugin_tools(plugin)

            # Call startup
            try:
                plugin.on_startup()
            except Exception as e:
                logger.warning(f"Plugin {plugin_id} on_startup error: {e}")

            plugin._set_status(PluginStatus.RUNNING)
            logger.info(f"Plugin {plugin_id} enabled")
            return True, "Plugin enabled successfully"

    def disable(self, plugin_id: str) -> Tuple[bool, str]:
        """Disable a plugin."""
        with self._lock:
            plugin = self.registry.get(plugin_id)
            if not plugin:
                return False, f"Plugin {plugin_id} not found"

            if plugin.status == PluginStatus.DISABLED:
                return True, "Already disabled"

            try:
                # Unregister tools
                self._unregister_plugin_tools(plugin)

                # Call plugin lifecycle
                success = plugin.on_disable()
                if not success:
                    logger.warning(f"Plugin {plugin_id} on_disable returned False")

                plugin._enabled = False
                plugin._set_status(PluginStatus.DISABLED)
                
                # Clean up context
                self._contexts.pop(plugin_id, None)
                plugin.set_context(None)

                logger.info(f"Plugin {plugin_id} disabled")
                return True, "Plugin disabled successfully"
            except Exception as e:
                plugin._set_error(str(e))
                logger.error(f"Plugin {plugin_id} disable failed: {e}")
                return False, f"Disable failed: {e}"

    # ============================================================
    # UNINSTALL
    # ============================================================

    def uninstall(self, plugin_id: str) -> Tuple[bool, str]:
        """Uninstall a plugin completely."""
        with self._lock:
            # Disable first if enabled
            plugin = self.registry.get(plugin_id)
            if plugin and plugin.status != PluginStatus.DISABLED:
                self.disable(plugin_id)

            # Unregister
            self.registry.unregister(plugin_id)

            # Remove config
            config_path = self._config_dir / f"{plugin_id}.json"
            if config_path.exists():
                config_path.unlink()

            # Uninstall from disk
            return self.loader.uninstall(plugin_id)

    # ============================================================
    # RELOAD
    # ============================================================

    def reload(self, plugin_id: str) -> Tuple[bool, str]:
        """Reload a plugin (disable -> enable)."""
        plugin = self.registry.get(plugin_id)
        if not plugin:
            return False, f"Plugin {plugin_id} not found"

        was_enabled = plugin.status == PluginStatus.RUNNING
        
        if was_enabled:
            self.disable(plugin_id)
        
        # Reload from disk
        self.registry.unregister(plugin_id)
        new_plugin, manifest, errors = self.loader.load_plugin(plugin_id, self.hercule_version)
        if not new_plugin:
            return False, f"Reload failed: {errors}"
        
        new_plugin.set_manifest(manifest)
        self.registry.register(new_plugin)
        
        # Restore config
        config = self.registry.load_config(plugin_id, str(self._config_dir))
        new_plugin.set_config(config)

        if was_enabled:
            return self.enable(plugin_id)
        
        return True, "Plugin reloaded (disabled)"

    # ============================================================
    # HEALTH
    # ============================================================

    def health(self, plugin_id: str) -> Dict[str, Any]:
        """Get plugin health information."""
        plugin = self.registry.get(plugin_id)
        if not plugin:
            return {"status": "not_found", "plugin_id": plugin_id}

        manifest = self.registry.get_manifest(plugin_id)
        activity = self.registry.get_activity(plugin_id, limit=10)

        health_info = plugin.health()
        health_info.update({
            "plugin_id": plugin_id,
            "version": plugin.version,
            "manifest_version": manifest.version if manifest else "unknown",
            "last_used": activity[-1]["timestamp"] if activity else None,
            "total_calls": len(activity),
        })
        return health_info

    def all_health(self) -> Dict[str, Dict[str, Any]]:
        """Get health for all plugins."""
        return {pid: self.health(pid) for pid in self.registry.names()}

    # ============================================================
    # PERMISSIONS
    # ============================================================

    def get_permissions(self, plugin_id: str) -> Dict[str, Any]:
        """Get permission status for a plugin."""
        manifest = self.registry.get_manifest(plugin_id)
        if not manifest:
            return {"error": "No manifest"}

        granted = []
        pending = []
        denied = []

        for perm in manifest.permissions:
            if self._permission_model.is_granted(plugin_id, manifest.version, perm):
                granted.append(perm)
            elif self._permission_model.is_sensitive(perm):
                approval = self._permission_model.get_approval(plugin_id, manifest.version, perm)
                if approval and approval.status == ApprovalStatus.PENDING:
                    pending.append(perm)
                elif approval and approval.status == ApprovalStatus.DENIED:
                    denied.append(perm)
                else:
                    pending.append(perm)
            else:
                # Non-sensitive permissions are auto-granted
                granted.append(perm)

        return {
            "plugin_id": plugin_id,
            "version": manifest.version,
            "granted": granted,
            "pending": pending,
            "denied": denied,
            "all_declared": manifest.permissions,
        }

    def approve_permission(self, plugin_id: str, permission: str) -> bool:
        """Approve a sensitive permission for a plugin."""
        manifest = self.registry.get_manifest(plugin_id)
        if not manifest:
            return False
        return self._permission_model.grant_approval(plugin_id, manifest.version, permission)

    def revoke_permission(self, plugin_id: str, permission: str) -> bool:
        """Revoke a permission for a plugin."""
        manifest = self.registry.get_manifest(plugin_id)
        if not manifest:
            return False
        return self._permission_model.revoke_approval(plugin_id, manifest.version, permission)

    # ============================================================
    # CONFIGURATION
    # ============================================================

    def update_config(self, plugin_id: str, config: Dict[str, Any]) -> Tuple[bool, str]:
        """Update plugin configuration."""
        plugin = self.registry.get(plugin_id)
        if not plugin:
            return False, "Plugin not found"

        # Validate against schema
        manifest = self.registry.get_manifest(plugin_id)
        if manifest and manifest.configuration_schema:
            # Basic schema validation
            for key, value in config.items():
                if key in manifest.configuration_schema:
                    expected_type = manifest.configuration_schema[key].get("type")
                    if expected_type and not isinstance(value, eval(expected_type)):
                        return False, f"Config key '{key}' expects type {expected_type}"

        self.registry.set_config(plugin_id, config)
        plugin.set_config(config)
        self.registry.save_config(plugin_id, str(self._config_dir))
        return True, "Configuration updated"

    # ============================================================
    # EXECUTION
    # ============================================================

    def execute(self, plugin_id: str, *args, **kwargs) -> Any:
        """Execute a plugin (backward compatibility)."""
        plugin = self.registry.get(plugin_id)
        if not plugin:
            raise ValueError(f"Plugin {plugin_id} not found")
        if plugin.status != PluginStatus.RUNNING:
            raise RuntimeError(f"Plugin {plugin_id} is not running (status: {plugin.status.value})")
        return plugin.execute(*args, **kwargs)

    # ============================================================
    # INTERNAL HELPERS
    # ============================================================

    def _create_context(
        self,
        plugin: Plugin,
        manifest: Optional[PluginManifest],
    ) -> PluginContext:
        """Create a controlled context for the plugin."""
        plugin_id = plugin.plugin_id
        
        # Logger
        plugin_logger = logging.getLogger(f"HERCULE.Plugin.{plugin_id}")

        # Config
        config = self.registry.get_config(plugin_id)

        # Events
        events = PluginEventBus(
            plugin_id=plugin_id,
            core_event_bus=self.registry._event_bus,
        )

        # Tools
        tools = PluginToolRegistry(
            plugin_id=plugin_id,
            ability_manager=self.registry._ability_manager,
        )

        # Memory
        memory = PluginMemoryAccess(
            plugin_id=plugin_id,
            memory_manager=self.registry._memory_manager,
        )

        # Permissions
        permissions = PluginPermissionChecker(
            plugin_id=plugin_id,
            plugin_version=manifest.version if manifest else "1.0.0",
            declared_permissions=manifest.permissions if manifest else [],
            permission_model=self._permission_model,
        )

        # Workspace
        workspace_path = self._workspace_dir / plugin_id
        workspace_path.mkdir(parents=True, exist_ok=True)
        workspace = PluginWorkspaceAccess(
            plugin_id=plugin_id,
            base_path=str(workspace_path),
            permissions=permissions,
        )

        # UI hooks
        ui_hooks = PluginUIHooks(plugin_id=plugin_id)

        # Model access
        model_access = None
        if self.registry._model_router:
            model_access = PluginModelAccess(
                plugin_id=plugin_id,
                model_router=self.registry._model_router,
                permission_checker=permissions,
            )

        return PluginContext(
            plugin_id=plugin_id,
            logger=plugin_logger,
            config=config,
            events=events,
            tools=tools,
            memory=memory,
            permissions=permissions,
            workspace=workspace,
            ui_hooks=ui_hooks,
            model_access=model_access,
        )

    def _register_plugin_tools(self, plugin: Plugin) -> None:
        """Register plugin tools through AbilityManager."""
        if not self.registry._ability_manager or not plugin.context:
            return

        tools_registry = plugin.context.tools
        # Plugin can register tools in on_enable
        # This is called by the plugin itself via context.tools.register_tool()

    def _unregister_plugin_tools(self, plugin: Plugin) -> None:
        """Unregister plugin tools from AbilityManager."""
        if not self.registry._ability_manager:
            return

        plugin_id = plugin.plugin_id
        # Directly unregister from AbilityManager by prefix
        ability_manager = self.registry._ability_manager
        for ability_name in list(ability_manager.registry._abilities.keys()):
            if ability_name.startswith(f"{plugin_id}."):
                ability_manager.unregister(ability_name)

        # Also clear local registry if context exists
        if plugin.context and hasattr(plugin.context, 'tools'):
            plugin.context.tools._registered_tools.clear()

    # ============================================================
    # COMPATIBILITY
    # ============================================================

    def check_compatibility(self, plugin_id: str) -> Tuple[bool, str]:
        """Check if plugin is compatible with current HERCULE version."""
        manifest = self.registry.get_manifest(plugin_id)
        if not manifest:
            return False, "No manifest"

        valid, errors = self.loader.validate(manifest, self.hercule_version)
        if not valid:
            return False, "; ".join(errors)
        return True, "Compatible"

    # ============================================================
    # UPDATE CHECK
    # ============================================================

    def check_update_permissions(
        self,
        plugin_id: str,
        new_manifest: PluginManifest,
    ) -> List[str]:
        """Check what new permissions an update would require."""
        old_manifest = self.registry.get_manifest(plugin_id)
        if not old_manifest:
            return [p for p in new_manifest.permissions if self._permission_model.is_sensitive(p)]

        return self._permission_model.check_permission_set_changed(
            plugin_id,
            old_manifest.version,
            new_manifest.version,
            old_manifest.permissions,
            new_manifest.permissions,
        )

    def update_plugin(self, plugin_id: str, source_path: str) -> Tuple[bool, str]:
        """Update a plugin from a new package/directory."""
        # Load new manifest to check permissions
        source = Path(source_path)
        if source.is_dir():
            manifest_path = source / "manifest.json"
        else:
            return False, "Update from package not yet supported"

        if not manifest_path.exists():
            return False, "No manifest in update source"

        import json
        with open(manifest_path, "r", encoding="utf-8") as f:
            new_manifest_data = json.load(f)
        new_manifest = PluginManifest.from_dict(new_manifest_data)

        # Check new permissions
        new_perms = self.check_update_permissions(plugin_id, new_manifest)
        if new_perms:
            return False, f"Update requires approval for new sensitive permissions: {new_perms}"

        # Perform update
        success, msg = self.loader.install(source, plugin_id, force=True)
        if not success:
            return False, msg

        # Reload
        return self.reload(plugin_id)

    # ============================================================
    # LISTING
    # ============================================================

    def list_installed(self) -> List[Dict[str, Any]]:
        """List all installed plugins with status."""
        result = []
        for plugin_id in self.loader.get_installed_plugins():
            plugin = self.registry.get(plugin_id)
            manifest = self.registry.get_manifest(plugin_id)
            result.append({
                "plugin_id": plugin_id,
                "name": manifest.name if manifest else plugin_id,
                "version": manifest.version if manifest else "unknown",
                "status": plugin.status.value if plugin else "INSTALLED",
                "enabled": plugin.enabled if plugin else False,
                "description": manifest.description if manifest else "",
            })
        return result

    def list_available(self, folder: Optional[str] = None) -> List[Dict[str, Any]]:
        """List available (not necessarily installed) plugins."""
        return self.discover(folder)


from pathlib import Path
from plugin_sdk.permissions import ApprovalStatus
from plugin_sdk.plugin import (
    PluginEventBus,
    PluginToolRegistry,
    PluginMemoryAccess,
    PluginWorkspaceAccess,
    PluginUIHooks,
    PluginContext,
)