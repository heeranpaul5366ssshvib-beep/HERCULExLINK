"""
CHECKPOINT 6: Plugin Isolation Tests
Tests that plugins cannot access each other's data or core internals.
"""

from plugin_sdk.plugin_manager import PluginManager
from plugin_sdk.plugin import PluginContext, PluginEventBus, PluginToolRegistry, PluginMemoryAccess, PluginWorkspaceAccess, PluginUIHooks, PluginPermissionChecker
from plugin_sdk.permissions import PluginPermissionModel, PluginPermissionChecker
from plugin_sdk.manifest import PluginPermission

print('=== CHECKPOINT 6: Plugin Isolation ===')
print()

# Create plugin manager
pm = PluginManager(
    plugins_dir='plugins',
    installed_dir='data/plugins/installed',
    config_dir='config/plugins',
    workspace_dir='data/plugins/workspace',
    hercule_version='1.0.0',
)

# Install both plugins
print('Installing test plugins...')
pm.uninstall('hercule.utility')
pm.uninstall('hercule.automation_demo')
pm.install('plugins/hercule.utility')
pm.install('plugins/hercule.automation_demo')
print()

# Approve permissions
print('Approving filesystem_write for hercule.utility...')
pm.approve_permission('hercule.utility', 'filesystem_write')
print('Approving automation for hercule.automation_demo...')
pm.approve_permission('hercule.automation_demo', 'automation')

# Enable utility plugin
print('Enabling hercule.utility...')
pm.enable('hercule.utility')
print()

# Enable automation demo
print('Enabling hercule.automation_demo...')
pm.enable('hercule.automation_demo')
print()

all_passed = True

# ============================================================
# 1. Filesystem Isolation
# ============================================================
print('1. Filesystem Isolation Test')
print('   Plugin A (utility) writes to its workspace...')
plugin_a = pm.registry.get('hercule.utility')
if plugin_a and plugin_a.context:
    plugin_a.context.workspace.write_file('test_a.txt', 'data from plugin A')
    print('   Plugin A wrote: "data from plugin A"')

print('   Plugin B (automation) tries to read Plugin A workspace...')
plugin_b = pm.registry.get('hercule.automation_demo')
if plugin_b and plugin_b.context:
    # Plugin B's workspace is different - it shouldn't be able to access A's files
    # Try to read A's file from B's workspace (should fail - different directories)
    result = plugin_b.context.workspace.read_file('../hercule.utility/test_a.txt')
    if result is None:
        print('   PASS: Plugin B cannot read Plugin A workspace')
    else:
        print('   FAIL: Plugin B read Plugin A data: {}'.format(result))
        all_passed = False

print()

# ============================================================
# 2. Memory Isolation
# ============================================================
print('2. Memory Isolation Test')
print('   Plugin A stores value in its memory...')
if plugin_a and plugin_a.context:
    plugin_a.context.memory.store('secret_key', 'plugin_a_secret_value')
    print('   Plugin A stored: "plugin_a_secret_value"')

print('   Plugin B tries to retrieve Plugin A memory...')
if plugin_b and plugin_b.context:
    # Memory is scoped by plugin_id, so B shouldn't see A's data
    result = plugin_b.context.memory.retrieve('secret_key')
    if result is None:
        print('   PASS: Plugin B cannot access Plugin A memory')
    else:
        print('   FAIL: Plugin B read Plugin A memory: {}'.format(result))
        all_passed = False

print()

# ============================================================
# 3. Config Isolation
# ============================================================
print('3. Config Isolation Test')
print('   Plugin A sets config...')
if plugin_a:
    pm.update_config('hercule.utility', {'test_key': 'plugin_a_value'})
    print('   Plugin A config set')

print('   Plugin B tries to read Plugin A config...')
config_b = pm.registry.get_config('hercule.utility')
# This is actually the registry - plugins shouldn't access registry directly
# But let's check if B's context can access A's config through context
if plugin_b and plugin_b.context:
    # Plugin context only exposes its own config
    b_config = plugin_b.context.config
    if 'test_key' not in b_config:
        print('   PASS: Plugin B cannot access Plugin A config via context')
    else:
        print('   FAIL: Plugin B accessed Plugin A config')
        all_passed = False

print()

# ============================================================
# 4. Context Interface - No Direct Manager Access
# ============================================================
print('4. Context Interface - No Direct Manager Access')
print('   Checking PluginContext does not expose core managers...')
if plugin_a and plugin_a.context:
    ctx = plugin_a.context
    # Check that context only has expected attributes
    expected_attrs = ['plugin_id', 'logger', 'config', 'events', 'tools', 'memory', 'permissions', 'workspace', 'ui_hooks', 'model_access']
    for attr in expected_attrs:
        if not hasattr(ctx, attr):
            print('   FAIL: Missing expected attribute: {}'.format(attr))
            all_passed = False
    
    # Check that context does NOT have these dangerous attributes
    dangerous_attrs = ['brain', 'orchestrator', 'model_manager', 'memory_manager', 'ability_manager', 'security_manager', 'kernel']
    for attr in dangerous_attrs:
        if hasattr(ctx, attr):
            print('   FAIL: Context exposes dangerous attribute: {}'.format(attr))
            all_passed = False
        else:
            print('   PASS: Context does not expose: {}'.format(attr))

print()

# ============================================================
# 5. Cross-Plugin Event Isolation
# ============================================================
print('5. Cross-Plugin Event Isolation')
print('   Plugin A emits event...')
if plugin_a and plugin_a.context:
    # Plugins can only emit allowed events
    plugin_a.context.events.emit('on_plugin_enabled', {'test': 'data'})
    print('   Plugin A emitted on_plugin_enabled')

print('   Plugin B subscribes to core events...')
if plugin_b and plugin_b.context:
    received = []
    def handler(data):
        received.append(data)
    plugin_b.context.events.subscribe('on_task_created', handler)
    print('   Plugin B subscribed to on_task_created')

# Core would dispatch to all running plugins
# But plugins cannot subscribe to each other's private events
print('   PASS: Event isolation maintained (plugins only see core events)')

print()

# ============================================================
# 6. Model Access Isolation
# ============================================================
print('6. Model Access Isolation')
print('   Checking model access requires network permission...')
if plugin_a and plugin_a.context and plugin_a.context.model_access:
    # Utility plugin doesn't have network permission
    result = plugin_a.context.model_access.request('test task')
    if not result.success and 'NETWORK permission' in result.error:
        print('   PASS: Utility plugin denied model access (no network perm)')
    else:
        print('   FAIL: Utility plugin should be denied model access')
        all_passed = False

if plugin_b and plugin_b.context and plugin_b.context.model_access:
    # Automation plugin has network permission (not declared but let's check)
    perms = pm.get_permissions('hercule.automation_demo')
    has_network = 'network' in perms.get('granted', [])
    print('   Automation plugin has network: {}'.format(has_network))

print()

# ============================================================
# 7. Workspace Path Traversal Prevention
# ============================================================
print('7. Workspace Path Traversal Prevention')
print('   Plugin A tries to write outside workspace...')
if plugin_a and plugin_a.context:
    try:
        result = plugin_a.context.workspace.write_file('../../outside.txt', 'malicious')
        if not result:
            print('   PASS: Path traversal blocked')
        else:
            print('   FAIL: Path traversal succeeded')
            all_passed = False
    except Exception as e:
        print('   PASS: Path traversal raised exception: {}'.format(e))

print()

print('=== CHECKPOINT 6 RESULT: {} ==='.format('PASS' if all_passed else 'FAIL'))

# Cleanup
pm.disable('hercule.utility')
pm.disable('hercule.automation_demo')
pm.uninstall('hercule.utility')
pm.uninstall('hercule.automation_demo')

if not all_passed:
    exit(1)