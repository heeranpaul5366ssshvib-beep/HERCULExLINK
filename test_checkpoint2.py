from plugin_sdk.plugin_manager import PluginManager

# Create plugin manager
pm = PluginManager(
    plugins_dir='plugins',
    installed_dir='data/plugins/installed',
    config_dir='config/plugins',
    workspace_dir='data/plugins/workspace',
    hercule_version='1.0.0',
)

print('=== CHECKPOINT 2: Reference Plugin A (hercule.utility) ===')
print()

# 1. Discover
print('1. Discovering plugins...')
discovered = pm.discover()
for p in discovered:
    if p.get('manifest') and p['manifest'].plugin_id == 'hercule.utility':
        print('   Found: {} v{} - valid={}'.format(p['manifest'].name, p['manifest'].version, p['valid']))
        break
else:
    print('   NOT FOUND')
print()

# 2. Validate
print('2. Validating plugin...')
valid, errors = pm.validate('hercule.utility')
print('   Valid: {}'.format(valid))
if errors:
    print('   Errors: {}'.format(errors))
print()

# 3. Install
print('3. Installing plugin...')
success, msg = pm.install('plugins/hercule.utility')
print('   Success: {}'.format(success))
print('   Message: {}'.format(msg))
print()

# 4. Enable
print('4. Enabling plugin...')
success, msg = pm.enable('hercule.utility')
print('   Success: {}'.format(success))
print('   Message: {}'.format(msg))
print()

# 5. Health check
print('5. Health check...')
health = pm.health('hercule.utility')
print('   Status: {}'.format(health.get('status')))
print('   Enabled: {}'.format(health.get('enabled')))
print('   Capabilities: {}'.format(health.get('capabilities')))
print('   Permissions: {}'.format(health.get('permissions')))
print()

# 6. Test calculator tool
print('6. Testing calculator tool registration...')
try:
    plugin = pm.registry.get('hercule.utility')
    if plugin and plugin.context:
        tools = plugin.context.tools._registered_tools
        if 'calculate' in tools:
            print('   Tool "calculate" registered')
        if 'system_info' in tools:
            print('   Tool "system_info" registered')
        if 'time_util' in tools:
            print('   Tool "time_util" registered')
except Exception as e:
    print('   Error: {}'.format(e))
print()

# 7. Disable
print('7. Disabling plugin...')
success, msg = pm.disable('hercule.utility')
print('   Success: {}'.format(success))
print('   Message: {}'.format(msg))
print()

# 8. Enable again
print('8. Enabling plugin again...')
success, msg = pm.enable('hercule.utility')
print('   Success: {}'.format(success))
print('   Message: {}'.format(msg))
print()

# 9. Uninstall
print('9. Uninstalling plugin...')
success, msg = pm.uninstall('hercule.utility')
print('   Success: {}'.format(success))
print('   Message: {}'.format(msg))
print()

# 10. Reinstall
print('10. Reinstalling plugin...')
success, msg = pm.install('plugins/hercule.utility')
print('   Success: {}'.format(success))
print('   Message: {}'.format(msg))
print()

# 11. Final uninstall
print('11. Final uninstall...')
success, msg = pm.uninstall('hercule.utility')
print('   Success: {}'.format(success))
print('   Message: {}'.format(msg))
print()

print('=== CHECKPOINT 2 COMPLETE ===')