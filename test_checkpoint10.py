"""
CHECKPOINT 10: Version/Permission Invalidation Tests
Test that version changes invalidate previous approvals.
"""

from plugin_sdk.plugin_manager import PluginManager
from abilities.ability_manager import AbilityManager
from security.permissions.policy_manager import PolicyManager
from plugin_sdk.permissions import PluginPermissionModel

print('=== CHECKPOINT 10: Version/Permission Invalidation ===')
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

# Also test the permission model directly
perm_model = PluginPermissionModel()

print('=== CHECKPOINT 10: Version/Permission Invalidation ===')
print()

all_passed = True

# ============================================================
# 1. Direct permission model test - version change invalidates approvals
# ============================================================
print('1. Direct permission model - version change invalidates approvals')
plugin_id = 'test.plugin'
old_version = '1.0.0'
new_version = '1.1.0'
old_perms = ['automation', 'secrets']
new_perms = ['automation', 'secrets', 'filesystem_write']

# Grant approvals for old version
for perm in old_perms:
    perm_model.grant_approval(plugin_id, old_version, perm)

# Verify old approvals exist
for perm in old_perms:
    if not perm_model.is_granted(plugin_id, old_version, perm):
        print(f'   FAIL: Old approval for {perm} not found')
        all_passed = False

# Check permission set changed (simulates version change)
new_sensitive = perm_model.check_permission_set_changed(
    plugin_id, old_version, new_version, old_perms, new_perms
)

# Old approvals should be revoked
for perm in old_perms:
    if perm_model.is_granted(plugin_id, old_version, perm):
        print(f'   FAIL: Old approval for {perm} should be revoked')
        all_passed = False

# New sensitive permissions should be returned
expected_new = ['automation', 'secrets', 'filesystem_write']
for perm in expected_new:
    if perm not in new_sensitive:
        print(f'   FAIL: New sensitive permission {perm} not in result')
        all_passed = False

print('   PASS: Version change invalidates old approvals')
print()

# ============================================================
# 2. Direct permission model test - same version, new permissions
# ============================================================
print('2. Direct permission model - same version, new permissions only')
perm_model2 = PluginPermissionModel()
plugin_id2 = 'test.plugin2'
version = '1.0.0'
old_perms2 = ['network']
new_perms2 = ['network', 'automation']

# Grant network (non-sensitive, auto-granted)
# Grant automation for old version
perm_model2.grant_approval(plugin_id2, version, 'automation')

# Check permission set changed (same version, new perms)
new_sensitive2 = perm_model2.check_permission_set_changed(
    plugin_id2, version, version, old_perms2, new_perms2
)

# Old approvals should NOT be revoked (same version)
if not perm_model2.is_granted(plugin_id2, version, 'automation'):
    print('   FAIL: Old approval should not be revoked for same version')
    all_passed = False

# Only newly requested sensitive permissions should be returned
if 'automation' not in new_sensitive2:
    print('   FAIL: New sensitive permission should be in result')
    all_passed = False

print('   PASS: Same version preserves old approvals, flags new sensitive perms')
print()

# ============================================================
# 3. Plugin manager integration - version change in update
# ============================================================
print('3. Plugin manager integration - version change in update')
# Install automation demo v1.0.0
pm.uninstall('hercule.automation_demo')
pm.install('plugins/hercule.automation_demo')

# Approve automation for v1.0.0
pm.approve_permission('hercule.automation_demo', 'automation')

# Verify approval granted
perms = pm.get_permissions('hercule.automation_demo')
if 'automation' not in perms.get('granted', []):
    print('   FAIL: Automation not granted for v1.0.0')
    all_passed = False

# Now simulate update to v1.1.0 by creating a new manifest object
from plugin_sdk.manifest import PluginManifest
old_manifest = pm.registry.get_manifest('hercule.automation_demo')
new_manifest = PluginManifest(
    plugin_id=old_manifest.plugin_id,
    name=old_manifest.name,
    version='1.1.0',  # Changed version
    description=old_manifest.description,
    author=old_manifest.author,
    entrypoint=old_manifest.entrypoint,
    capabilities=old_manifest.capabilities,
    permissions=old_manifest.permissions,
    dependencies=old_manifest.dependencies,
    configuration_schema=old_manifest.configuration_schema,
)

# Check update permissions - should detect version change and require re-approval
new_perms = pm.check_update_permissions('hercule.automation_demo', new_manifest)
if 'automation' not in new_perms:
    print('   FAIL: Version change should require re-approval for automation')
    all_passed = False
else:
    print('   PASS: Plugin manager detects version change requiring re-approval')

print()

# ============================================================
# 4. Plugin manager - same version, new sensitive permission
# ============================================================
print('4. Plugin manager - same version, new sensitive permission')
# Reinstall automation demo
pm.uninstall('hercule.automation_demo')
pm.install('plugins/hercule.automation_demo')

# Approve automation
pm.approve_permission('hercule.automation_demo', 'automation')

# Create new manifest with same version but new sensitive permission (secrets, not already in manifest)
old_manifest = pm.registry.get_manifest('hercule.automation_demo')
new_manifest = PluginManifest(
    plugin_id=old_manifest.plugin_id,
    name=old_manifest.name,
    version=old_manifest.version,  # Same version
    description=old_manifest.description,
    author=old_manifest.author,
    entrypoint=old_manifest.entrypoint,
    capabilities=old_manifest.capabilities,
    permissions=old_manifest.permissions + ['secrets'],  # New sensitive perm (not in original)
    dependencies=old_manifest.dependencies,
    configuration_schema=old_manifest.configuration_schema,
)

# Check update permissions
new_perms = pm.check_update_permissions('hercule.automation_demo', new_manifest)
if 'secrets' not in new_perms:
    print('   FAIL: New sensitive permission should require approval')
    all_passed = False
else:
    print('   PASS: New sensitive permission requires approval')

# automation should NOT be in new_perms (already approved, same version)
if 'automation' in new_perms:
    print('   FAIL: Already approved permission should not require re-approval')
    all_passed = False
else:
    print('   PASS: Already approved permission does not require re-approval')

print()

# Cleanup
pm.uninstall('hercule.automation_demo')

print()
print('=== CHECKPOINT 10 RESULT: {} ==='.format('PASS' if all_passed else 'FAIL'))

if not all_passed:
    exit(1)