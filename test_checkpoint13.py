"""
CHECKPOINT 13: Health Monitoring Tests
Test health state changes accurately for healthy, failed, disabled, etc.
"""

from plugin_sdk.plugin_manager import PluginManager
from abilities.ability_manager import AbilityManager
from security.permissions.policy_manager import PolicyManager
from plugin_sdk.plugin import PluginStatus

print('=== CHECKPOINT 13: Health Monitoring ===')
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

print('=== CHECKPOINT 13: Health Monitoring ===')
print()

all_passed = True

# ============================================================
# 1. Healthy plugin
# ============================================================
print('1. Healthy plugin')
pm.uninstall('hercule.utility')
pm.install('plugins/hercule.utility')
pm.approve_permission('hercule.utility', 'filesystem_write')
pm.enable('hercule.utility')

health = pm.health('hercule.utility')
if health.get('status') == 'running' and health.get('enabled') == True:
    print('   PASS: Healthy plugin shows running status')
else:
    print('   FAIL: Healthy plugin status:', health)
    all_passed = False

# Check health has required fields
required_fields = ['status', 'version', 'enabled', 'permissions', 'capabilities', 'last_error', 'total_calls']
for field in required_fields:
    if field not in health:
        print(f'   FAIL: Missing health field: {field}')
        all_passed = False

print()

# ============================================================
# 2. Disabled plugin
# ============================================================
print('2. Disabled plugin')
pm.disable('hercule.utility')

health = pm.health('hercule.utility')
if health.get('status') == 'disabled' and health.get('enabled') == False:
    print('   PASS: Disabled plugin shows disabled status')
else:
    print('   FAIL: Disabled plugin status:', health)
    all_passed = False
print()

# ============================================================
# 3. Plugin with initialization failure
# ============================================================
print('3. Plugin with initialization failure')
# Create a plugin that fails on_enable
import json
import tempfile
from pathlib import Path

with tempfile.TemporaryDirectory() as tmpdir:
    fail_plugin_dir = Path(tmpdir) / 'fail_plugin'
    fail_plugin_dir.mkdir()
    
    manifest = {
        "plugin_id": "test.fail_plugin",
        "name": "Fail Plugin",
        "version": "1.0.0",
        "description": "Plugin that fails on enable",
        "author": "Test",
        "entrypoint": "plugin",
        "capabilities": [],
        "permissions": [],
    }
    
    with open(fail_plugin_dir / 'manifest.json', 'w') as f:
        json.dump(manifest, f)
    
    with open(fail_plugin_dir / 'plugin.py', 'w') as f:
        f.write('''
from plugin_sdk.plugin import Plugin

class FailPlugin(Plugin):
    def on_enable(self):
        return False  # Always fail
    def execute(self, *args, **kwargs):
        return "ok"
''')
    
    pm.install(str(fail_plugin_dir))
    success, msg = pm.enable('test.fail_plugin')
    if not success:
        print('   PASS: Failed enable detected')
    else:
        print('   FAIL: Should have failed to enable')
        all_passed = False
    
    health = pm.health('test.fail_plugin')
    if health.get('status') == 'failed':
        print('   PASS: Failed plugin shows failed status')
    else:
        print('   FAIL: Failed plugin status:', health)
        all_passed = False

pm.uninstall('test.fail_plugin')
print()

# ============================================================
# 4. Plugin with runtime exception
# ============================================================
print('4. Plugin with runtime exception')
with tempfile.TemporaryDirectory() as tmpdir:
    exception_plugin_dir = Path(tmpdir) / 'exception_plugin'
    exception_plugin_dir.mkdir()
    
    manifest = {
        "plugin_id": "test.exception_plugin",
        "name": "Exception Plugin",
        "version": "1.0.0",
        "description": "Plugin that raises exception",
        "author": "Test",
        "entrypoint": "plugin",
        "capabilities": ["custom"],
        "permissions": [],
    }
    
    with open(exception_plugin_dir / 'manifest.json', 'w') as f:
        json.dump(manifest, f)
    
    with open(exception_plugin_dir / 'plugin.py', 'w') as f:
        f.write('''
from plugin_sdk.plugin import Plugin

class ExceptionPlugin(Plugin):
    def on_enable(self):
        raise RuntimeError("Simulated crash")
    def execute(self, *args, **kwargs):
        return "ok"
''')
    
    pm.install(str(exception_plugin_dir))
    success, msg = pm.enable('test.exception_plugin')
    if not success:
        print('   PASS: Exception during enable caught')
    else:
        print('   FAIL: Exception should have been caught')
        all_passed = False
    
    health = pm.health('test.exception_plugin')
    if health.get('status') == 'failed':
        print('   PASS: Exception plugin shows failed status')
    else:
        print('   FAIL: Exception plugin status:', health)
        all_passed = False

pm.uninstall('test.exception_plugin')
print()

# ============================================================
# 5. Invalid configuration
# ============================================================
print('5. Plugin with invalid configuration')
pm.install('plugins/hercule.utility')
# Try to update config with wrong type
success, msg = pm.update_config('hercule.utility', {'default_precision': 'not_a_number'})
if not success:
    print('   PASS: Invalid config rejected')
else:
    print('   FAIL: Invalid config should be rejected')
    all_passed = False

pm.uninstall('hercule.utility')
print()

# ============================================================
# 6. Permission denial
# ============================================================
print('6. Permission denial health')
pm.install('plugins/hercule.automation_demo')
# Don't approve automation
pm.enable('hercule.automation_demo')  # Should fail

health = pm.health('hercule.automation_demo')
if health.get('status') in ['failed', 'disabled', 'permission_denied']:
    print('   PASS: Permission denial reflected in health')
else:
    print('   FAIL: Permission denial not reflected:', health)
    all_passed = False

pm.uninstall('hercule.automation_demo')
print()

# ============================================================
# 7. all_health() method
# ============================================================
print('7. all_health() method')
pm.install('plugins/hercule.utility')
pm.approve_permission('hercule.utility', 'filesystem_write')
pm.enable('hercule.utility')

all_health = pm.all_health()
if 'hercule.utility' in all_health:
    print('   PASS: all_health() includes plugin')
else:
    print('   FAIL: all_health() missing plugin')
    all_passed = False

pm.disable('hercule.utility')
pm.uninstall('hercule.utility')

print()

print('=== CHECKPOINT 13 RESULT: {} ==='.format('PASS' if all_passed else 'FAIL'))

if not all_passed:
    exit(1)