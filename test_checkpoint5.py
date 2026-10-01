"""
CHECKPOINT 5: Adversarial Permission Security Tests
Tests that all sensitive permissions fail closed when not approved.
"""

from plugin_sdk.plugin_manager import PluginManager
from plugin_sdk.permissions import PluginPermissionModel, PluginPermissionChecker
from plugin_sdk.manifest import PluginPermission

print('=== CHECKPOINT 5: Adversarial Permission Security ===')
print()

# Create plugin manager
pm = PluginManager(
    plugins_dir='plugins',
    installed_dir='data/plugins/installed',
    config_dir='config/plugins',
    workspace_dir='data/plugins/workspace',
    hercule_version='1.0.0',
)

# Install automation demo (has automation + clipboard)
print('Installing automation demo for testing...')
pm.install('plugins/hercule.automation_demo')

# Test each sensitive permission
sensitive_perms = [
    PluginPermission.SHELL.value,
    PluginPermission.PROCESS_EXECUTION.value,
    PluginPermission.FILESYSTEM_WRITE.value,
    PluginPermission.SECRETS.value,
    PluginPermission.MICROPHONE.value,
    PluginPermission.CAMERA.value,
    PluginPermission.AUTOMATION.value,
]

print('Testing PluginPermissionChecker with UNAPPROVED sensitive permissions:')
print()

all_passed = True

for perm in sensitive_perms:
    # Create a permission checker with the sensitive permission declared but not approved
    checker = PluginPermissionChecker(
        plugin_id='test.adversarial',
        plugin_version='1.0.0',
        declared_permissions=[perm],
        permission_model=pm._permission_model,
    )
    
    # Test has() - should return False
    has_result = checker.has(perm)
    
    # Test check() - should raise PermissionError
    check_raised = False
    try:
        checker.check(perm)
    except PermissionError:
        check_raised = True
    except Exception as e:
        print('  {}: check() raised unexpected exception: {}'.format(perm, e))
        check_raised = False
    
    # Test get_granted - should not include the permission
    granted = checker.get_granted()
    granted_correct = perm not in granted
    
    # Test get_pending - should include the permission
    pending = checker.get_pending()
    pending_correct = perm in pending
    
    passed = (not has_result) and check_raised and granted_correct and pending_correct
    all_passed = all_passed and passed
    
    status = 'PASS' if passed else 'FAIL'
    print('  {}: has={}, check_raised={}, granted_correct={}, pending_correct={} [{}]'.format(
        perm, has_result, check_raised, granted_correct, pending_correct, status
    ))

print()
print('Testing NETWORK (non-sensitive) permission - should be auto-granted:')
checker_net = PluginPermissionChecker(
    plugin_id='test.adversarial',
    plugin_version='1.0.0',
    declared_permissions=[PluginPermission.NETWORK.value],
    permission_model=pm._permission_model,
)
net_has = checker_net.has(PluginPermission.NETWORK.value)
net_granted = PluginPermission.NETWORK.value in checker_net.get_granted()
net_pending = PluginPermission.NETWORK.value in checker_net.get_pending()
print('  network: has={}, granted={}, pending={} [{}]'.format(
    net_has, net_granted, net_pending, 'PASS' if (net_has and net_granted and not net_pending) else 'FAIL'
))
all_passed = all_passed and net_has and net_granted and not net_pending

print()
print('Testing permission INDEPENDENCE (network does not grant shell):')
checker_both = PluginPermissionChecker(
    plugin_id='test.adversarial',
    plugin_version='1.0.0',
    declared_permissions=[PluginPermission.NETWORK.value, PluginPermission.SHELL.value],
    permission_model=pm._permission_model,
)
net_ok = checker_both.has(PluginPermission.NETWORK.value)
shell_denied = not checker_both.has(PluginPermission.SHELL.value)
print('  network granted: {}, shell denied: {} [{}]'.format(
    net_ok, shell_denied, 'PASS' if (net_ok and shell_denied) else 'FAIL'
))
all_passed = all_passed and net_ok and shell_denied

print()
print('Testing PluginPermissionModel.is_granted directly:')
model = pm._permission_model
for perm in sensitive_perms:
    granted = model.is_granted('test.adversarial', '1.0.0', perm)
    status = 'PASS' if not granted else 'FAIL'
    print('  {}: granted={} [{}]'.format(perm, granted, status))
    all_passed = all_passed and not granted

# Network should be granted (non-sensitive)
net_granted = model.is_granted('test.adversarial', '1.0.0', PluginPermission.NETWORK.value)
print('  network: granted={} [{}]'.format(net_granted, 'PASS' if net_granted else 'FAIL'))
all_passed = all_passed and net_granted

print()
print('Testing UNDECLARED permission access (should fail):')
checker_undeclared = PluginPermissionChecker(
    plugin_id='test.adversarial',
    plugin_version='1.0.0',
    declared_permissions=[PluginPermission.NETWORK.value],
    permission_model=pm._permission_model,
)
undeclared_raised = False
try:
    checker_undeclared.check(PluginPermission.SHELL.value)
except PermissionError:
    undeclared_raised = True
print('  Undeclared shell check() raised PermissionError: {} [{}]'.format(
    undeclared_raised, 'PASS' if undeclared_raised else 'FAIL'
))
all_passed = all_passed and undeclared_raised

print()
print('=== CHECKPOINT 5 RESULT: {} ==='.format('PASS' if all_passed else 'FAIL'))

if not all_passed:
    print('FAIL: Some adversarial tests failed')
    exit(1)