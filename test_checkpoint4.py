from plugin_sdk.plugin_manager import PluginManager

# Create plugin manager
pm = PluginManager(
    plugins_dir='plugins',
    installed_dir='data/plugins/installed',
    config_dir='config/plugins',
    workspace_dir='data/plugins/workspace',
    hercule_version='1.0.0',
)

print('=== CHECKPOINT 4: Reference Plugin C (hercule.automation_demo) ===')
print()

# 1. Discover
print('1. Discovering plugins...')
discovered = pm.discover()
for p in discovered:
    if p.get('manifest') and p['manifest'].plugin_id == 'hercule.automation_demo':
        print('   Found: {} v{} - valid={}'.format(p['manifest'].name, p['manifest'].version, p['valid']))
        break
else:
    print('   NOT FOUND')
print()

# 2. Install
print('2. Installing plugin...')
success, msg = pm.install('plugins/hercule.automation_demo')
print('   Success: {}'.format(success))
print('   Message: {}'.format(msg))
print()

# 3. Try to enable WITHOUT approval (should fail - automation is sensitive)
print('3. Attempting to enable WITHOUT automation approval...')
success, msg = pm.enable('hercule.automation_demo')
print('   Success: {}'.format(success))
print('   Message: {}'.format(msg))
print()

# 4. Check permissions - should show automation as pending
print('4. Checking permissions (automation should be pending)...')
perms = pm.get_permissions('hercule.automation_demo')
print('   Granted: {}'.format(perms.get('granted')))
print('   Pending: {}'.format(perms.get('pending')))
print('   Denied: {}'.format(perms.get('denied')))
print()

# 5. Approve automation permission
print('5. Approving automation permission...')
success = pm.approve_permission('hercule.automation_demo', 'automation')
print('   Success: {}'.format(success))
print()

# 6. Check permissions again
print('6. Checking permissions after approval...')
perms = pm.get_permissions('hercule.automation_demo')
print('   Granted: {}'.format(perms.get('granted')))
print('   Pending: {}'.format(perms.get('pending')))
print()

# 7. Now enable should work
print('7. Enabling plugin with automation approved...')
success, msg = pm.enable('hercule.automation_demo')
print('   Success: {}'.format(success))
print('   Message: {}'.format(msg))
print()

# 8. Test automation tool (should work now)
print('8. Testing automation tool (safe_automation)...')
plugin = pm.registry.get('hercule.automation_demo')
if plugin and plugin.context:
    # Check if automation permission is granted
    has_auto = plugin.context.permissions.has('automation')
    print('   Has automation permission: {}'.format(has_auto))
    
    # Try to call the tool handler directly
    result = plugin._safe_automation_handler("noop")
    print('   Tool result: {}'.format(result))
    print('   Approved: {}'.format(result.get('approved')))
print()

# 9. Attempt operation that requires automation without permission (simulate by revoking)
print('9. Revoking automation permission...')
success = pm.revoke_permission('hercule.automation_demo', 'automation')
print('   Success: {}'.format(success))
print()

# 10. Check permissions after revoke
print('10. Checking permissions after revoke...')
perms = pm.get_permissions('hercule.automation_demo')
print('   Granted: {}'.format(perms.get('granted')))
print('   Pending: {}'.format(perms.get('pending')))
print()

# 11. Try automation tool again (should fail)
print('11. Testing automation tool after revoke...')
plugin = pm.registry.get('hercule.automation_demo')
if plugin and plugin.context:
    has_auto = plugin.context.permissions.has('automation')
    print('   Has automation permission: {}'.format(has_auto))
    result = plugin._safe_automation_handler("noop")
    print('   Tool result: {}'.format(result))
    print('   Approved: {}'.format(result.get('approved')))
print()

# 12. Change plugin version (simulate update) - should invalidate approval
print('12. Simulating version change (v1.0.0 -> v1.1.0)...')
# We'll manually test the version invalidation by checking the permission model
from plugin_sdk.permissions import PluginPermissionModel
perm_model = PluginPermissionModel()
# Check old version approval
old_granted = perm_model.is_granted('hercule.automation_demo', '1.0.0', 'automation')
print('   Old version (1.0.0) automation granted: {}'.format(old_granted))

# Simulate version change
new_perms = perm_model.check_permission_set_changed(
    'hercule.automation_demo', '1.0.0', '1.1.0',
    ['automation', 'clipboard'],
    ['automation', 'clipboard']
)
print('   New sensitive perms after version change: {}'.format(new_perms))
print('   Old version automation granted after change: {}'.format(perm_model.is_granted('hercule.automation_demo', '1.0.0', 'automation')))
print()

# 13. Disable and uninstall
print('13. Disabling plugin...')
success, msg = pm.disable('hercule.automation_demo')
print('   Success: {}'.format(success))
print()

print('14. Uninstalling plugin...')
success, msg = pm.uninstall('hercule.automation_demo')
print('   Success: {}'.format(success))
print('   Message: {}'.format(msg))
print()

print('=== CHECKPOINT 4 COMPLETE ===')