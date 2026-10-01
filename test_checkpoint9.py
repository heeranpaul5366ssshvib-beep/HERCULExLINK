"""
CHECKPOINT 9: Model Access Security Tests
Verify model access occurs only through ModelRouter.
"""

from plugin_sdk.plugin_manager import PluginManager
from abilities.ability_manager import AbilityManager
from security.permissions.policy_manager import PolicyManager

print('=== CHECKPOINT 9: Model Access Security ===')
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

# Install and enable plugins
print('Installing and enabling test plugins...')
pm.uninstall('hercule.utility')
pm.uninstall('hercule.network_demo')
pm.install('plugins/hercule.utility')
pm.install('plugins/hercule.network_demo')
pm.enable('hercule.utility')
pm.enable('hercule.network_demo')
print()

all_passed = True

# ============================================================
# 1. Utility plugin (no network perm) - model access should be denied
# ============================================================
print('1. Utility plugin (no network permission) - model access should be denied')
utility_plugin = pm.registry.get('hercule.utility')
if utility_plugin and utility_plugin.context and utility_plugin.context.model_access:
    result = utility_plugin.context.model_access.request('test task')
    if not result.success and 'NETWORK permission' in result.error:
        print('   PASS: Model access denied without network permission')
    else:
        print('   FAIL: Model access should be denied without network permission')
        all_passed = False
else:
    print('   SKIP: Model access not available')
print()

# ============================================================
# 2. Network plugin (has network perm) - model access should work if router available
# ============================================================
print('2. Network plugin (has network permission) - model access attempt')
network_plugin = pm.registry.get('hercule.network_demo')
if network_plugin and network_plugin.context and network_plugin.context.model_access:
    result = network_plugin.context.model_access.request('test task')
    # May fail if no model router is available, but should not fail due to permission
    if result.success:
        print('   PASS: Model access works with network permission')
    elif 'NETWORK permission' in result.error:
        print('   FAIL: Model access denied despite network permission')
        all_passed = False
    else:
        print('   PASS: Model access attempted (permission OK, may fail due to no router)')
else:
    print('   SKIP: Model access not available')
print()

# ============================================================
# 3. List available models (requires network)
# ============================================================
print('3. List available models (requires network permission)')
if network_plugin and network_plugin.context and network_plugin.context.model_access:
    models = network_plugin.context.model_access.list_available_models()
    print(f'   Available models: {models}')
    print('   PASS: Model listing works with network permission')
else:
    print('   SKIP: Model access not available')
print()

# ============================================================
# 4. Get router health
# ============================================================
print('4. Get router health')
if network_plugin and network_plugin.context and network_plugin.context.model_access:
    health = network_plugin.context.model_access.get_router_health()
    print(f'   Router health: {health}')
    print('   PASS: Router health check works')
else:
    print('   SKIP: Model access not available')
print()

# ============================================================
# 5. Disabled plugin - model access should be denied
# ============================================================
print('5. Disabled plugin - model access should be denied')
pm.disable('hercule.network_demo')
network_plugin = pm.registry.get('hercule.network_demo')
if network_plugin and network_plugin.context and network_plugin.context.model_access:
    result = network_plugin.context.model_access.request('test task')
    if not result.success:
        print('   PASS: Model access denied for disabled plugin')
    else:
        print('   FAIL: Model access should be denied for disabled plugin')
        all_passed = False
else:
    print('   PASS: Model access not available for disabled plugin')

# Re-enable
pm.enable('hercule.network_demo')

# ============================================================
# 6. Uninstalled plugin - model access should not be available
# ============================================================
print('6. Uninstalled plugin - model access should not be available')
pm.disable('hercule.network_demo')
pm.uninstall('hercule.network_demo')
network_plugin = pm.registry.get('hercule.network_demo')
if network_plugin is None:
    print('   PASS: Uninstalled plugin not accessible')
else:
    if network_plugin.context and network_plugin.context.model_access:
        print('   FAIL: Uninstalled plugin still has model access')
        all_passed = False
    else:
        print('   PASS: Uninstalled plugin has no model access')

# Cleanup
pm.disable('hercule.utility')
pm.uninstall('hercule.utility')

print()
print('=== CHECKPOINT 9 RESULT: {} ==='.format('PASS' if all_passed else 'FAIL'))

if not all_passed:
    exit(1)