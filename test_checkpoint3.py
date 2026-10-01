from plugin_sdk.plugin_manager import PluginManager

# Create plugin manager
pm = PluginManager(
    plugins_dir='plugins',
    installed_dir='data/plugins/installed',
    config_dir='config/plugins',
    workspace_dir='data/plugins/workspace',
    hercule_version='1.0.0',
)

print('=== CHECKPOINT 3: Reference Plugin B (hercule.network_demo) ===')
print()

# 1. Discover
print('1. Discovering plugins...')
discovered = pm.discover()
for p in discovered:
    if p.get('manifest') and p['manifest'].plugin_id == 'hercule.network_demo':
        print('   Found: {} v{} - valid={}'.format(p['manifest'].name, p['manifest'].version, p['valid']))
        break
else:
    print('   NOT FOUND')
print()

# 2. Validate
print('2. Validating plugin...')
valid, errors = pm.validate('hercule.network_demo')
print('   Valid: {}'.format(valid))
if errors:
    print('   Errors: {}'.format(errors))
print()

# 3. Install
print('3. Installing plugin...')
success, msg = pm.install('plugins/hercule.network_demo')
print('   Success: {}'.format(success))
print('   Message: {}'.format(msg))
print()

# 4. Try to enable WITHOUT network approval (should fail if network is sensitive, but network is non-sensitive)
print('4. Enabling plugin (network is non-sensitive, should auto-grant)...')
success, msg = pm.enable('hercule.network_demo')
print('   Success: {}'.format(success))
print('   Message: {}'.format(msg))
print()

# 5. Check permissions
print('5. Checking permissions...')
perms = pm.get_permissions('hercule.network_demo')
print('   Granted: {}'.format(perms.get('granted')))
print('   Pending: {}'.format(perms.get('pending')))
print('   Denied: {}'.format(perms.get('denied')))
print()

# 6. Test network tool (should work since network is auto-granted)
print('6. Testing network tool registration...')
plugin = pm.registry.get('hercule.network_demo')
if plugin and plugin.context:
    tools = plugin.context.tools._registered_tools
    for name in ['http_get', 'http_post']:
        if name in tools:
            print('   Tool "{}" registered'.format(name))
        else:
            print('   Tool "{}" NOT found'.format(name))
print()

# 7. Verify shell/process execution remains denied (not in permissions)
print('7. Verifying shell/process execution NOT granted...')
perms = pm.get_permissions('hercule.network_demo')
all_perms = perms.get('all_declared', [])
if 'shell' not in all_perms and 'process_execution' not in all_perms:
    print('   PASS: shell and process_execution not declared')
else:
    print('   FAIL: sensitive permissions found in manifest')
print()

# 8. Disable
print('8. Disabling plugin...')
success, msg = pm.disable('hercule.network_demo')
print('   Success: {}'.format(success))
print('   Message: {}'.format(msg))
print()

# 9. Uninstall
print('9. Uninstalling plugin...')
success, msg = pm.uninstall('hercule.network_demo')
print('   Success: {}'.format(success))
print('   Message: {}'.format(msg))
print()

print('=== CHECKPOINT 3 COMPLETE ===')