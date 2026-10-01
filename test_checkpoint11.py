"""
CHECKPOINT 11: Update Safety Tests
Test safe successful and failed update behavior.
"""

from plugin_sdk.plugin_manager import PluginManager
from abilities.ability_manager import AbilityManager
from security.permissions.policy_manager import PolicyManager
from plugin_sdk.manifest import PluginManifest
import shutil
from pathlib import Path

print('=== CHECKPOINT 11: Update Safety ===')
print()

# Create plugin manager with AbilityManager
ability_manager = AbilityManager(PolicyManager())
pm = PluginManager(
    plugins_dir='plugins',
    installed_dir='data/plugins/installed',
    config_dir='config/plugins',
    workspace_dir='data/plugins/workspace',
    hercule_version='1.0.0',
    ability_manager=ability_manager,
)

print('=== CHECKPOINT 11: Update Safety ===')
print()

all_passed = True

# ============================================================
# 1. Successful update - v1.0.0 to v1.1.0 (same permissions, version bump)
# ============================================================
print('1. Successful update - version bump, same permissions')
pm.uninstall('hercule.utility')
pm.install('plugins/hercule.utility')

# Approve filesystem_write for utility
pm.approve_permission('hercule.utility', 'filesystem_write')
pm.enable('hercule.utility')

# Create new manifest with version bump
old_manifest = pm.registry.get_manifest('hercule.utility')
new_manifest = PluginManifest(
    plugin_id=old_manifest.plugin_id,
    name=old_manifest.name,
    version='1.1.0',  # Version bump
    description=old_manifest.description,
    author=old_manifest.author,
    entrypoint=old_manifest.entrypoint,
    capabilities=old_manifest.capabilities,
    permissions=old_manifest.permissions,  # Same permissions
    dependencies=old_manifest.dependencies,
    configuration_schema=old_manifest.configuration_schema,
)

# Check update permissions - version change means ALL sensitive perms need re-approval
new_perms = pm.check_update_permissions('hercule.utility', new_manifest)
if 'filesystem_write' in new_perms:
    print('   PASS: Version bump requires re-approval for ALL sensitive permissions')
else:
    print('   FAIL: Version bump should require re-approval for sensitive permissions')
    all_passed = False

# Cleanup for next test
pm.disable('hercule.utility')
pm.uninstall('hercule.utility')
print()

# ============================================================
# 2. Successful update - same version, same permissions (no change)
# ============================================================
print('2. Successful update - same version, same permissions (no change)')
pm.install('plugins/hercule.utility')
pm.approve_permission('hercule.utility', 'filesystem_write')
pm.enable('hercule.utility')

old_manifest = pm.registry.get_manifest('hercule.utility')
new_manifest = PluginManifest(
    plugin_id=old_manifest.plugin_id,
    name=old_manifest.name,
    version=old_manifest.version,  # SAME version
    description=old_manifest.description,
    author=old_manifest.author,
    entrypoint=old_manifest.entrypoint,
    capabilities=old_manifest.capabilities,
    permissions=old_manifest.permissions,  # Same permissions
    dependencies=old_manifest.dependencies,
    configuration_schema=old_manifest.configuration_schema,
)

# Check update permissions - same version, same perms = no new approvals needed
new_perms = pm.check_update_permissions('hercule.utility', new_manifest)
if len(new_perms) == 0:
    print('   PASS: Same version, same permissions = no new approvals needed')
else:
    print('   FAIL: Unexpected new permissions:', new_perms)
    all_passed = False

# Cleanup
pm.disable('hercule.utility')
pm.uninstall('hercule.utility')
print()
print('=== CHECKPOINT 11 RESULT: {} ==='.format('PASS' if all_passed else 'FAIL'))

if not all_passed:
    exit(1)