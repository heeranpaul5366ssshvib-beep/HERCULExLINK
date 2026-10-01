from abilities.ability_manager import AbilityManager
from abilities.terminal.terminal_ability import TerminalAbility

am = AbilityManager()
am.register(TerminalAbility())

# Test quota with allowlisted command
print('Testing resource quota on terminal...')
for i in range(5):
    result = am.execute('terminal', 'python --version', approval_required=True, approved=True)
    if isinstance(result, dict) and result.get('status') == 'failed':
        print('Call {}: Failed - {}'.format(i+1, result.get('error')))
        break
    else:
        quota = result.get('quota', {})
        usage = quota.get('usage', {})
        print('Call {}: OK - calls: {}'.format(i+1, usage.get('calls', 0)))

print('Quota status:', am.quota_manager.get_usage_report('ability', 'terminal'))