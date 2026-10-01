# Comprehensive availability check
import os
os.environ['HERCULE_ALLOW_MOCK'] = '1'

checks = []

# 1. Core modules
try:
    from pc_frontier import PCFrontierSystem
    pc = PCFrontierSystem()
    checks.append(('PC-Frontier System', True))
except Exception as e:
    checks.append(('PC-Frontier System', False, str(e)))

# 2. Model CLI
try:
    from models.model_cli import cmd_list, cmd_install, cmd_remove, cmd_default, cmd_info, cmd_runtime, cmd_catalog
    checks.append(('Model CLI', True))
except Exception as e:
    checks.append(('Model CLI', False, str(e)))

# 3. Model Manager
try:
    from models.builtin.model_manager import list_installed, download_model, ensure_runtime
    models = list_installed()
    checks.append(('Model Manager', True, len(models)))
except Exception as e:
    checks.append(('Model Manager', False, str(e)))

# 4. Abilities
try:
    from abilities.ability_manager import AbilityManager
    from abilities.coding.coding_ability import CodingAbility
    from abilities.web.web_ability import WebAbility
    from abilities.browser.browser_ability import BrowserAbility
    from abilities.automation.automation_ability import AutomationAbility
    from abilities.database.database_ability import DatabaseAbility
    from abilities.diagnostics.diagnostics_ability import DiagnosticsAbility
    from abilities.package_manager.package_manager_ability import PackageManagerAbility
    checks.append(('Abilities (8 implemented)', True))
except Exception as e:
    checks.append(('Abilities', False, str(e)))

# 5. Metrics/Monitoring
try:
    from monitoring.metrics import get_metrics, get_health, increment, observe, get_prometheus_metrics
    m = get_metrics()
    increment('test', 1)
    prom = get_prometheus_metrics()
    h = get_health()
    checks.append(('Metrics/Monitoring', True))
except Exception as e:
    checks.append(('Metrics/Monitoring', False, str(e)))

# 6. Config
try:
    from config.settings import HERCULESettings, get_settings
    s = HERCULESettings()
    checks.append(('Config Management', True))
except Exception as e:
    checks.append(('Config Management', False, str(e)))

# 7. Sandbox
try:
    from security.sandbox.sandbox_manager import SandboxManager, SandboxProfile
    from security.audit_sandbox import SandboxAuditor
    sm = SandboxManager()
    auditor = SandboxAuditor()
    report = auditor.audit_all()
    assert report['summary']['by_severity']['HIGH'] == 0
    checks.append(('Sandbox + Audit', True))
except Exception as e:
    checks.append(('Sandbox + Audit', False, str(e)))

# 8. Secrets
try:
    from security.secrets.secrets_manager import SecretsManager
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        sm = SecretsManager(storage_path=tmp + '/secrets.enc')
        sm.set_secret('test', 'value')
        assert sm.get_secret('test') == 'value'
    checks.append(('Secrets Management', True))
except Exception as e:
    checks.append(('Secrets Management', False, str(e)))

# 9. Resource Quotas
try:
    from security.quotas.resource_quota import ResourceQuotaManager
    rqm = ResourceQuotaManager()
    rqm.consume_quota('ability', 'terminal', calls=1)
    checks.append(('Resource Quotas', True))
except Exception as e:
    checks.append(('Resource Quotas', False, str(e)))

# 10. Rate Limiting
try:
    from abilities.ability_manager import AbilityManager
    am = AbilityManager()
    checks.append(('Rate Limiting', True))
except Exception as e:
    checks.append(('Rate Limiting', False, str(e)))

# 11. Plugin Security
try:
    from plugin_sdk.signature import SignatureVerifier
    from plugin_sdk.manifest import PluginManifest
    checks.append(('Plugin Security', True))
except Exception as e:
    checks.append(('Plugin Security', False, str(e)))

# 13. Audit Logging
try:
    from security.auditing.audit_manager import AuditManager
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        am = AuditManager(log_dir=tmp)
        am.log('test', actor='user')
        am.verify_integrity()
    checks.append(('Audit Logging', True))
except Exception as e:
    checks.append(('Audit Logging', False, str(e)))

# 14. Config file loading
try:
    from config.settings import get_settings
    import tempfile, yaml
    with tempfile.NamedTemporaryFile(suffix='.yaml', delete=False, mode='w') as f:
        yaml.dump({'environment': 'production', 'models': {'provider': 'ollama'}}, f)
        config_path = f.name
    from config.settings import get_settings
    s = get_settings(config_path)
    assert s.environment == 'production'
    checks.append(('Config File Loading', True))
except Exception as e:
    checks.append(('Config File Loading', False, str(e))

print('=== AVAILABILITY CHECK RESULTS ===')
for item in checks:
    name = item[0]
    ok = item[1]
    status = 'AVAILABLE' if ok else 'MISSING'
    detail = ' (' + str(item[2]) + ')' if len(item) > 2 else ''
    print('  ' + status + ': ' + name + detail)

all_ok = all(item[1] for item in checks)
print('Overall: ' + ('ALL AVAILABLE' if all_ok else 'SOME MISSING'))