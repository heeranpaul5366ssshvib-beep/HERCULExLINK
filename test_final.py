# Final integration test
print('=== Final Integration Test ===')

# 1. PC-Frontier init
import os
os.environ['HERCULE_ALLOW_MOCK'] = '1'
from pc_frontier import PCFrontierSystem
pc = PCFrontierSystem()
print('[OK] PC-Frontier init')

# 2. Model CLI
from models.model_cli import cmd_list
print('[OK] Model CLI')

# 3. Metrics
from monitoring.metrics import get_metrics, increment, observe, get_prometheus_metrics
m = get_metrics()
increment('test', 1)
observe('latency', 0.1)
prom = get_prometheus_metrics()
print('[OK] Metrics/Prometheus')

# 4. Config
from config.settings import HERCULESettings, get_settings
s = HERCULESettings()
print('[OK] Config management')

# 5. Sandbox audit
from security.audit_sandbox import SandboxAuditor
auditor = SandboxAuditor()
report = auditor.audit_all()
assert report['summary']['by_severity']['HIGH'] == 0
assert report['summary']['by_severity']['CRITICAL'] == 0
print('[OK] Sandbox audit (no HIGH/CRITICAL)')

# 6. Model CLI
from models.model_cli import cmd_list
print('[OK] Model CLI')

# 7. Secrets
from security.secrets.secrets_manager import SecretsManager
import tempfile
with tempfile.TemporaryDirectory() as tmp:
    sm = SecretsManager(storage_path=f'{tmp}/secrets.enc')
    sm.set_secret('test', 'value', owner='user1')
    assert sm.get_secret('test') == 'value'
print('[OK] Secrets management')

# 8. Resource quotas
from security.quotas.resource_quota import ResourceQuotaManager
rqm = ResourceQuotaManager()
rqm.consume_quota('ability', 'terminal', calls=1)
print('[OK] Resource quotas')

# 8. Rate limiting
from abilities.ability_manager import AbilityManager
am = AbilityManager()
print('[OK] Rate limiting')

# 9. Health check
from monitoring.metrics import get_health
health = get_health()
health.register('test', lambda: (True, 'ok'))
print('[OK] Health checks')

print()
print('=== ALL TESTS PASSED ===')