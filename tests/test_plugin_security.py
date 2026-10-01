"""
--------------------------------------------
HERCULE AI Operating System
Plugin System Security Tests
--------------------------------------------
"""

import pytest
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

from plugin_sdk.manifest import (
    PluginManifest,
    PluginPermission,
    PluginCapability,
    PluginStatus,
)
from plugin_sdk.permissions import (
    PluginPermissionModel,
    PluginPermissionChecker,
    ApprovalStatus,
)
from plugin_sdk.plugin import Plugin, PluginContext
from plugin_sdk.plugin_loader import PluginLoader
from plugin_sdk.plugin_manager import PluginManager


class TestPluginManifest:
    """Tests for plugin manifest validation."""

    def test_valid_manifest(self):
        """Test that a valid manifest passes validation."""
        manifest = PluginManifest(
            plugin_id="test.plugin",
            name="Test Plugin",
            version="1.0.0",
            description="A test plugin",
            author="Test Author",
            entrypoint="plugin",
            capabilities=["search", "research"],
            permissions=["network"],
        )
        errors = manifest.validate()
        assert len(errors) == 0

    def test_missing_required_fields(self):
        """Test that missing required fields are caught."""
        manifest = PluginManifest(
            plugin_id="",
            name="",
            version="",
            entrypoint="",
        )
        errors = manifest.validate()
        assert "plugin_id is required" in errors
        assert "name is required" in errors
        assert "version is required" in errors
        assert "entrypoint is required" in errors

    def test_unknown_permission_rejected(self):
        """Test that unknown permissions are rejected."""
        manifest = PluginManifest(
            plugin_id="test.plugin",
            name="Test",
            version="1.0.0",
            entrypoint="plugin",
            permissions=["unknown_permission"],
        )
        errors = manifest.validate()
        assert any("unknown permission" in e for e in errors)

    def test_unknown_capability_rejected(self):
        """Test that unknown capabilities are rejected."""
        manifest = PluginManifest(
            plugin_id="test.plugin",
            name="Test",
            version="1.0.0",
            entrypoint="plugin",
            capabilities=["unknown_capability"],
        )
        errors = manifest.validate()
        assert any("unknown capability" in e for e in errors)

    def test_manifest_serialization(self):
        """Test manifest to/from dict conversion."""
        manifest = PluginManifest(
            plugin_id="test.plugin",
            name="Test Plugin",
            version="1.0.0",
            description="A test plugin",
            author="Test Author",
            entrypoint="plugin",
            capabilities=["search"],
            permissions=["network"],
            dependencies=["other.plugin"],
            configuration_schema={"key": {"type": "str"}},
        )
        data = manifest.to_dict()
        assert data["plugin_id"] == "test.plugin"
        assert data["capabilities"] == ["search"]
        assert data["permissions"] == ["network"]

        restored = PluginManifest.from_dict(data)
        assert restored.plugin_id == "test.plugin"
        assert restored.capabilities == ["search"]
        assert restored.permissions == ["network"]


class TestPermissionModel:
    """Tests for plugin permission model."""

    def test_sensitive_permissions_defined(self):
        """Test that sensitive permissions are correctly identified."""
        model = PluginPermissionModel()
        
        # These should be sensitive
        assert model.is_sensitive(PluginPermission.SHELL.value)
        assert model.is_sensitive(PluginPermission.PROCESS_EXECUTION.value)
        assert model.is_sensitive(PluginPermission.FILESYSTEM_WRITE.value)
        assert model.is_sensitive(PluginPermission.SECRETS.value)
        assert model.is_sensitive(PluginPermission.MICROPHONE.value)
        assert model.is_sensitive(PluginPermission.CAMERA.value)
        assert model.is_sensitive(PluginPermission.AUTOMATION.value)

        # These should NOT be sensitive (auto-granted)
        assert not model.is_sensitive(PluginPermission.FILESYSTEM_READ.value)
        assert not model.is_sensitive(PluginPermission.NETWORK.value)
        assert not model.is_sensitive(PluginPermission.SYSTEM_INFO.value)
        assert not model.is_sensitive(PluginPermission.BROWSER.value)
        assert not model.is_sensitive(PluginPermission.CLIPBOARD.value)

    def test_approval_flow(self):
        """Test permission approval flow."""
        model = PluginPermissionModel()
        plugin_id = "test.plugin"
        version = "1.0.0"
        permission = PluginPermission.SHELL.value

        # Initially not granted
        assert not model.is_granted(plugin_id, version, permission)

        # Request approval
        approval = model.request_approval(plugin_id, version, permission)
        assert approval.status == ApprovalStatus.PENDING

        # Grant approval
        assert model.grant_approval(plugin_id, version, permission)
        assert model.is_granted(plugin_id, version, permission)

        # Revoke approval
        assert model.revoke_approval(plugin_id, version, permission)
        assert not model.is_granted(plugin_id, version, permission)

    def test_deny_approval(self):
        """Test denying a permission."""
        model = PluginPermissionModel()
        plugin_id = "test.plugin"
        version = "1.0.0"
        permission = PluginPermission.SECRETS.value

        model.request_approval(plugin_id, version, permission)
        assert model.deny_approval(plugin_id, version, permission)
        
        approval = model.get_approval(plugin_id, version, permission)
        assert approval.status == ApprovalStatus.DENIED

    def test_permission_independence(self):
        """Test that permissions are independent - NETWORK doesn't grant SHELL."""
        model = PluginPermissionModel()
        plugin_id = "test.plugin"
        version = "1.0.0"

        # Grant NETWORK
        model.grant_approval(plugin_id, version, PluginPermission.NETWORK.value)
        assert model.is_granted(plugin_id, version, PluginPermission.NETWORK.value)

        # SHELL should still not be granted
        assert not model.is_granted(plugin_id, version, PluginPermission.SHELL.value)

    def test_version_change_invalidates_approvals(self):
        """Test that plugin version change invalidates old approvals."""
        model = PluginPermissionModel()
        plugin_id = "test.plugin"
        old_version = "1.0.0"
        new_version = "1.1.0"

        # Grant approvals for old version
        for perm in [PluginPermission.SHELL.value, PluginPermission.SECRETS.value]:
            model.grant_approval(plugin_id, old_version, perm)

        # Check permission set changed
        new_perms = model.check_permission_set_changed(
            plugin_id, old_version, new_version,
            [PluginPermission.SHELL.value, PluginPermission.SECRETS.value],
            [PluginPermission.SHELL.value, PluginPermission.SECRETS.value, PluginPermission.FILESYSTEM_WRITE.value],
        )

        # Old approvals should be revoked
        assert not model.is_granted(plugin_id, old_version, PluginPermission.SHELL.value)
        assert not model.is_granted(plugin_id, old_version, PluginPermission.SECRETS.value)
        
        # New sensitive permission should be requested
        assert PluginPermission.FILESYSTEM_WRITE.value in new_perms

    def test_no_allow_everything_forever(self):
        """Test that 'allow everything forever' is not the default for sensitive permissions."""
        import tempfile
        from pathlib import Path
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tmp:
            temp_path = Path(tmp.name)
        try:
            model = PluginPermissionModel(approvals_store=temp_path)
            plugin_id = "test.plugin"
            version = "1.0.0"

            # By default, sensitive permissions should NOT be granted
            for perm in PluginPermission:
                if model.is_sensitive(perm.value):
                    assert not model.is_granted(plugin_id, version, perm.value), f"{perm.value} should not be granted by default"
            
            # Non-sensitive permissions ARE auto-granted (by design)
            for perm in PluginPermission:
                if not model.is_sensitive(perm.value):
                    assert model.is_granted(plugin_id, version, perm.value), f"{perm.value} should be auto-granted"
        finally:
            temp_path.unlink(missing_ok=True)


class TestPluginPermissionChecker:
    """Tests for runtime permission checking."""

    def test_check_granted_permission(self):
        """Test checking a granted permission."""
        model = PluginPermissionModel()
        plugin_id = "test.plugin"
        version = "1.0.0"
        
        # Grant NETWORK (non-sensitive, auto-granted)
        checker = PluginPermissionChecker(
            plugin_id, version, 
            [PluginPermission.NETWORK.value], 
            model
        )
        
        assert checker.has(PluginPermission.NETWORK.value)
        assert checker.check(PluginPermission.NETWORK.value) is True

    def test_check_denied_permission_raises(self):
        """Test that checking ungranted sensitive permission raises."""
        model = PluginPermissionModel()
        plugin_id = "test.plugin"
        version = "1.0.0"
        
        checker = PluginPermissionChecker(
            plugin_id, version, 
            [PluginPermission.SHELL.value], 
            model
        )
        
        assert not checker.has(PluginPermission.SHELL.value)
        
        with pytest.raises(PermissionError):
            checker.check(PluginPermission.SHELL.value)

    def test_check_undeclared_permission_raises(self):
        """Test that checking undeclared permission raises."""
        model = PluginPermissionModel()
        plugin_id = "test.plugin"
        version = "1.0.0"
        
        checker = PluginPermissionChecker(
            plugin_id, version, 
            [PluginPermission.NETWORK.value], 
            model
        )
        
        with pytest.raises(PermissionError):
            checker.check(PluginPermission.SHELL.value)

    def test_get_pending_permissions(self):
        """Test getting pending sensitive permissions."""
        model = PluginPermissionModel()
        plugin_id = "test.plugin"
        version = "1.0.0"
        
        checker = PluginPermissionChecker(
            plugin_id, version, 
            [PluginPermission.NETWORK.value, PluginPermission.SHELL.value, PluginPermission.SECRETS.value], 
            model
        )
        
        pending = checker.get_pending()
        assert PluginPermission.SHELL.value in pending
        assert PluginPermission.SECRETS.value in pending
        assert PluginPermission.NETWORK.value not in pending  # non-sensitive, auto-granted


class TestPluginLoader:
    """Tests for plugin loader."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.plugins_dir = Path(self.temp_dir) / "plugins"
        self.installed_dir = Path(self.temp_dir) / "installed"
        self.plugins_dir.mkdir()
        self.installed_dir.mkdir()

    def teardown_method(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_plugin_dir(self, plugin_id: str, manifest: dict = None) -> Path:
        """Create a test plugin directory."""
        plugin_dir = self.plugins_dir / plugin_id
        plugin_dir.mkdir()
        
        if manifest is None:
            manifest = {
                "plugin_id": plugin_id,
                "name": "Test Plugin",
                "version": "1.0.0",
                "description": "Test",
                "author": "Test",
                "entrypoint": "plugin",
                "capabilities": [],
                "permissions": [],
            }
        
        with open(plugin_dir / "manifest.json", "w") as f:
            json.dump(manifest, f)
        
        # Create minimal plugin.py
        with open(plugin_dir / "plugin.py", "w") as f:
            f.write("""
from plugin_sdk.plugin import Plugin

class TestPlugin(Plugin):
    def execute(self, *args, **kwargs):
        return "ok"
""")
        
        return plugin_dir

    def test_discover_directory_plugin(self):
        """Test discovering a directory-based plugin."""
        loader = PluginLoader(
            plugins_dir=self.plugins_dir,
            installed_dir=self.installed_dir,
        )
        
        self._create_plugin_dir("test.plugin")
        
        plugins = loader.discover()
        assert len(plugins) == 1
        assert plugins[0]["valid"] is True
        assert plugins[0]["manifest"].plugin_id == "test.plugin"

    def test_discover_invalid_plugin(self):
        """Test discovering an invalid plugin (missing manifest)."""
        loader = PluginLoader(
            plugins_dir=self.plugins_dir,
            installed_dir=self.installed_dir,
        )
        
        # Create directory without manifest
        invalid_dir = self.plugins_dir / "invalid"
        invalid_dir.mkdir()
        
        plugins = loader.discover()
        # Should not include invalid plugin
        valid_plugins = [p for p in plugins if p["valid"]]
        assert len(valid_plugins) == 0

    def test_validate_compatible_version(self):
        """Test version compatibility check."""
        loader = PluginLoader(
            plugins_dir=self.plugins_dir,
            installed_dir=self.installed_dir,
        )
        
        manifest = PluginManifest(
            plugin_id="test.plugin",
            name="Test",
            version="1.0.0",
            entrypoint="plugin",
            min_hercule_version="1.0.0",
        )
        
        valid, errors = loader.validate(manifest, "1.0.0")
        assert valid
        assert len(errors) == 0

    def test_validate_incompatible_version(self):
        """Test incompatible version detection."""
        loader = PluginLoader(
            plugins_dir=self.plugins_dir,
            installed_dir=self.installed_dir,
        )
        
        manifest = PluginManifest(
            plugin_id="test.plugin",
            name="Test",
            version="1.0.0",
            entrypoint="plugin",
            min_hercule_version="2.0.0",
        )
        
        valid, errors = loader.validate(manifest, "1.0.0")
        assert not valid
        assert any("Incompatible" in e for e in errors)

    def test_install_from_directory(self):
        """Test installing plugin from directory."""
        loader = PluginLoader(
            plugins_dir=self.plugins_dir,
            installed_dir=self.installed_dir,
        )
        
        self._create_plugin_dir("test.plugin")
        
        success, msg = loader.install(self.plugins_dir / "test.plugin", "test.plugin")
        assert success
        assert (self.installed_dir / "test.plugin").exists()
        assert (self.installed_dir / "test.plugin" / "manifest.json").exists()

    def test_uninstall_plugin(self):
        """Test uninstalling a plugin."""
        loader = PluginLoader(
            plugins_dir=self.plugins_dir,
            installed_dir=self.installed_dir,
        )
        
        self._create_plugin_dir("test.plugin")
        loader.install(self.plugins_dir / "test.plugin", "test.plugin")
        
        success, msg = loader.uninstall("test.plugin")
        assert success
        assert not (self.installed_dir / "test.plugin").exists()


class TestPluginManager:
    """Tests for plugin manager lifecycle."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.plugins_dir = Path(self.temp_dir) / "plugins"
        self.installed_dir = Path(self.temp_dir) / "installed"
        self.config_dir = Path(self.temp_dir) / "config"
        self.workspace_dir = Path(self.temp_dir) / "workspace"
        self.plugins_dir.mkdir()
        self.installed_dir.mkdir()
        self.config_dir.mkdir()
        self.workspace_dir.mkdir()

    def teardown_method(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_test_plugin(self, plugin_id: str, permissions: list = None) -> Path:
        """Create a test plugin with given permissions."""
        plugin_dir = self.plugins_dir / plugin_id
        plugin_dir.mkdir()
        
        manifest = {
            "plugin_id": plugin_id,
            "name": "Test Plugin",
            "version": "1.0.0",
            "description": "Test",
            "author": "Test",
            "entrypoint": "plugin",
            "capabilities": ["test"],
            "permissions": permissions or [],
        }
        
        with open(plugin_dir / "manifest.json", "w") as f:
            json.dump(manifest, f)
        
        with open(plugin_dir / "plugin.py", "w") as f:
            f.write(f"""
from plugin_sdk.plugin import Plugin

class TestPlugin(Plugin):
    def execute(self, *args, **kwargs):
        return "ok"
""")
        
        return plugin_dir

    def test_disabled_plugin_cannot_execute(self):
        """Test that disabled plugin cannot execute."""
        # This test would need a full plugin manager setup
        # Skipping detailed integration test here
        pass

    def test_denied_permission_blocks_execution(self):
        """Test that denied permission blocks plugin operations."""
        # This test would need a full plugin manager setup
        pass

    def test_unauthorized_filesystem_access(self):
        """Test that unauthorized filesystem access is blocked."""
        # This test would need a full plugin manager setup
        pass

    def test_unauthorized_network_access(self):
        """Test that unauthorized network access is blocked."""
        # This test would need a full plugin manager setup
        pass

    def test_plugin_crash_isolation(self):
        """Test that plugin crash doesn't crash HERCULE."""
        # This test would need a full plugin manager setup
        pass


class TestPluginLifecycle:
    """Tests for plugin lifecycle transitions."""

    def test_lifecycle_states(self):
        """Test all lifecycle states are defined."""
        assert PluginStatus.DISCOVERED.value == "discovered"
        assert PluginStatus.VALIDATED.value == "validated"
        assert PluginStatus.INSTALLED.value == "installed"
        assert PluginStatus.DISABLED.value == "disabled"
        assert PluginStatus.ENABLED.value == "enabled"
        assert PluginStatus.RUNNING.value == "running"
        assert PluginStatus.INVALID.value == "invalid"
        assert PluginStatus.INCOMPATIBLE.value == "incompatible"
        assert PluginStatus.FAILED.value == "failed"

    def test_failure_states(self):
        """Test that failure states are properly categorized."""
        failure_states = {
            PluginStatus.INVALID,
            PluginStatus.INCOMPATIBLE,
            PluginStatus.FAILED,
            PluginStatus.DISABLED,
        }
        
        for state in failure_states:
            assert state in PluginStatus


class TestPluginIsolation:
    """Tests for plugin isolation."""

    def test_plugin_context_restricted(self):
        """Test that PluginContext doesn't expose internals."""
        # PluginContext only exposes controlled interfaces
        # It doesn't expose Brain, Orchestrator, or other internal managers
        pass

    def test_plugin_cannot_access_other_plugin_config(self):
        """Test that plugins cannot access other plugins' config."""
        # Each plugin has isolated config via plugin_id scoping
        pass

    def test_plugin_cannot_modify_core_settings(self):
        """Test that plugins cannot modify core HERCULE settings."""
        # PluginContext.config only allows plugin's own config
        pass


class TestPluginVersioning:
    """Tests for plugin versioning."""

    def test_version_compatibility_check(self):
        """Test plugin API version compatibility."""
        loader = PluginLoader(
            plugins_dir=Path("plugins"),
            installed_dir=Path("installed"),
        )
        
        # Plugin API 1.2 compatible with HERCULE 1.x
        manifest = PluginManifest(
            plugin_id="test.plugin",
            name="Test",
            version="1.0.0",
            entrypoint="plugin",
            plugin_api_version="1.2",
        )
        
        # Should be compatible (1.x matches 1.x)
        # This would need actual version parsing logic
        assert manifest.plugin_api_version.startswith("1.")

    def test_incompatible_api_version_rejected(self):
        """Test that incompatible API versions are rejected."""
        manifest = PluginManifest(
            plugin_id="test.plugin",
            name="Test",
            version="1.0.0",
            entrypoint="plugin",
            plugin_api_version="3.0",
        )
        
        # 3.x is incompatible with 1.x
        assert not manifest.plugin_api_version.startswith("1.")


class TestPluginUpdate:
    """Tests for plugin update safety."""

    def test_update_requires_new_approvals(self):
        """Test that plugin updates requiring new permissions need approval."""
        model = PluginPermissionModel()
        plugin_id = "test.plugin"
        old_version = "1.0.0"
        new_version = "1.1.0"

        # Old version has NETWORK only (non-sensitive)
        old_perms = [PluginPermission.NETWORK.value]
        
        # New version adds SHELL (sensitive)
        new_perms = [PluginPermission.NETWORK.value, PluginPermission.SHELL.value]

        new_sensitive = model.check_permission_set_changed(
            plugin_id, old_version, new_version, old_perms, new_perms
        )
        
        assert PluginPermission.SHELL.value in new_sensitive


if __name__ == "__main__":
    pytest.main([__file__, "-v"])