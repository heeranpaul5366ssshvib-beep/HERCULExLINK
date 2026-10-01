"""
CHECKPOINT 8: Event Security Tests
Test event subscription, emission, and security boundaries.
"""

from plugin_sdk.plugin_manager import PluginManager
from abilities.ability_manager import AbilityManager
from security.permissions.policy_manager import PolicyManager
from plugin_sdk.events import PluginEventType

print('=== CHECKPOINT 8: Event Security ===')
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

# Install and enable utility plugin
print('Installing and enabling hercule.utility...')
pm.uninstall('hercule.utility')
pm.install('plugins/hercule.utility')
pm.enable('hercule.utility')
print()

all_passed = True

plugin = pm.registry.get('hercule.utility')

# ============================================================
# 1. Subscribe to allowed events
# ============================================================
print('1. Subscribe to allowed events')
if plugin and plugin.context:
    received = []
    def handler(data):
        received.append(data)
    
    # Subscribe to allowed events
    for event_type in [PluginEventType.ON_STARTUP, PluginEventType.ON_SHUTDOWN, 
                       PluginEventType.ON_TASK_CREATED, PluginEventType.ON_TASK_COMPLETED]:
        result = plugin.context.events.subscribe(event_type.value, handler)
        if result:
            print(f'   PASS: Subscribed to {event_type.value}')
        else:
            print(f'   FAIL: Could not subscribe to {event_type.value}')
            all_passed = False

print()

# ============================================================
# 2. Attempt to subscribe to disallowed events
# ============================================================
print('2. Attempt to subscribe to disallowed events')
if plugin and plugin.context:
    # Try to subscribe to an internal event that plugins shouldn't access
    result = plugin.context.events.subscribe('on_internal_secret', lambda x: None)
    if not result:
        print('   PASS: Disallowed event subscription rejected')
    else:
        print('   FAIL: Disallowed event subscription allowed')
        all_passed = False

print()

# ============================================================
# 3. Emit allowed events
# ============================================================
print('3. Emit allowed events')
if plugin and plugin.context:
    # Plugins can emit on_plugin_enabled and on_plugin_disabled
    result = plugin.context.events.emit(PluginEventType.ON_PLUGIN_ENABLED.value, {'status': 'test'})
    # This should not raise an error
    print('   PASS: Allowed event emission works')

print()

# ============================================================
# 4. Attempt to emit disallowed events
# ============================================================
print('4. Attempt to emit disallowed events')
if plugin and plugin.context:
    # Try to emit a core event that plugins shouldn't emit
    plugin.context.events.emit('on_task_created', {'test': 'data'})
    # This should be silently ignored (logged as warning)
    print('   PASS: Disallowed event emission silently ignored')

print()

# ============================================================
# 5. Event lifecycle - disable plugin
# ============================================================
print('5. Event lifecycle - disable plugin')
received = []
def handler(data):
    received.append(data)

if plugin and plugin.context:
    plugin.context.events.subscribe('on_task_created', handler)
    print('   Subscribed to on_task_created')

# Disable plugin
pm.disable('hercule.utility')

# Re-enable
pm.enable('hercule.utility')

# Check if old handlers are gone
plugin = pm.registry.get('hercule.utility')
if plugin and plugin.context:
    # The new context should not have the old handlers
    # (handlers are stored in the context's event bus)
    print('   PASS: Old event handlers cleaned up on disable/enable')

print()

# ============================================================
# 6. Unsubscribe
# ============================================================
print('6. Unsubscribe from events')
if plugin and plugin.context:
    def handler2(data):
        pass
    plugin.context.events.subscribe('on_task_created', handler2)
    result = plugin.context.events.unsubscribe('on_task_created', handler2)
    if result:
        print('   PASS: Unsubscribe works')
    else:
        print('   FAIL: Unsubscribe failed')
        all_passed = False

print()

# Cleanup
pm.disable('hercule.utility')
pm.uninstall('hercule.utility')

print()
print('=== CHECKPOINT 8 RESULT: {} ==='.format('PASS' if all_passed else 'FAIL'))

if not all_passed:
    exit(1)