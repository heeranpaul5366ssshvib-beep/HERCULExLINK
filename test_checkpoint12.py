"""
CHECKPOINT 12: Package Security Tests
Test plugin installation from local directory and ZIP package.
Verify path traversal protection.
"""

from plugin_sdk.plugin_manager import PluginManager
from abilities.ability_manager import AbilityManager
from security.permissions.policy_manager import PolicyManager
import zipfile
import tempfile
import shutil
from pathlib import Path

print('=== CHECKPOINT 12: Package Security ===')
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

print('=== CHECKPOINT 12: Package Security ===')
print()

all_passed = True

# ============================================================
# 1. Install from local directory
# ============================================================
print('1. Install from local directory')
pm.uninstall('hercule.utility')
success, msg = pm.install('plugins/hercule.utility')
if success:
    print('   PASS: Directory installation works')
else:
    print('   FAIL: Directory installation failed:', msg)
    all_passed = False

# Verify installation
pm.uninstall('hercule.utility')
print()

# ============================================================
# 2. Install from ZIP package
# ============================================================
print('2. Install from ZIP package')
# Create a ZIP package from the utility plugin
with tempfile.TemporaryDirectory() as tmpdir:
    zip_path = Path(tmpdir) / 'hercule.utility.zip'
    with zipfile.ZipFile(zip_path, 'w') as zf:
        for file_path in Path('plugins/hercule.utility').rglob('*'):
            if file_path.is_file():
                arcname = file_path.relative_to(Path('plugins/hercule.utility').parent)
                zf.write(file_path, arcname)
    
    # Install from ZIP
    success, msg = pm.install(str(zip_path), 'hercule.utility')
    if success:
        print('   PASS: ZIP package installation works')
    else:
        print('   FAIL: ZIP installation failed:', msg)
        all_passed = False

pm.uninstall('hercule.utility')
print()

# ============================================================
# 3. Path traversal in ZIP - ../evil.txt
# ============================================================
print('3. Path traversal in ZIP - ../evil.txt')
with tempfile.TemporaryDirectory() as tmpdir:
    zip_path = Path(tmpdir) / 'evil.zip'
    with zipfile.ZipFile(zip_path, 'w') as zf:
        # Create a malicious ZIP with path traversal
        zf.writestr('../evil.txt', 'malicious content')
        # Also add a valid manifest to make it look like a plugin
        zf.writestr('manifest.json', '{"plugin_id": "evil", "name": "Evil", "version": "1.0.0", "entrypoint": "plugin", "capabilities": [], "permissions": []}')
    
    # Try to install - should be rejected
    success, msg = pm.install(str(zip_path), 'evil')
    if not success:
        print('   PASS: Path traversal (../) rejected:', msg[:80])
    else:
        print('   FAIL: Path traversal was allowed')
        all_passed = False
        # Cleanup if it somehow installed
        pm.uninstall('evil')
print()

# ============================================================
# 4. Path traversal in ZIP - ../../outside_file
# ============================================================
print('4. Path traversal in ZIP - ../../outside_file')
with tempfile.TemporaryDirectory() as tmpdir:
    zip_path = Path(tmpdir) / 'evil2.zip'
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.writestr('../../outside_file', 'malicious content')
        zf.writestr('manifest.json', '{"plugin_id": "evil2", "name": "Evil2", "version": "1.0.0", "entrypoint": "plugin", "capabilities": [], "permissions": []}')
    
    success, msg = pm.install(str(zip_path), 'evil2')
    if not success:
        print('   PASS: Path traversal (../../) rejected:', msg[:80])
    else:
        print('   FAIL: Path traversal was allowed')
        all_passed = False
        pm.uninstall('evil2')
print()

# ============================================================
# 5. Absolute paths in ZIP
# ============================================================
print('5. Absolute paths in ZIP')
with tempfile.TemporaryDirectory() as tmpdir:
    zip_path = Path(tmpdir) / 'evil3.zip'
    with zipfile.ZipFile(zip_path, 'w') as zf:
        # Absolute path (Windows style)
        zf.writestr('C:\\Windows\\system32\\evil.dll', 'malicious')
        zf.writestr('manifest.json', '{"plugin_id": "evil3", "name": "Evil3", "version": "1.0.0", "entrypoint": "plugin", "capabilities": [], "permissions": []}')
    
    success, msg = pm.install(str(zip_path), 'evil3')
    if not success:
        print('   PASS: Absolute path rejected:', msg[:80])
    else:
        print('   FAIL: Absolute path was allowed')
        all_passed = False
        pm.uninstall('evil3')
print()

# ============================================================
# 6. Duplicate plugin ID handling
# ============================================================
print('6. Duplicate plugin ID handling')
pm.install('plugins/hercule.utility')
success, msg = pm.install('plugins/hercule.utility')
if not success and 'already installed' in msg:
    print('   PASS: Duplicate installation rejected')
else:
    print('   FAIL: Duplicate installation should be rejected:', msg)
    all_passed = False

# Force install should work
success, msg = pm.install('plugins/hercule.utility', force=True)
if success:
    print('   PASS: Force install works')
else:
    print('   FAIL: Force install should work:', msg)
    all_passed = False

pm.uninstall('hercule.utility')
print()

# ============================================================
# 7. Plugin ID validation
# ============================================================
print('7. Plugin ID validation')
# Try to install a plugin with mismatched ID
with tempfile.TemporaryDirectory() as tmpdir:
    zip_path = Path(tmpdir) / 'mismatch.zip'
    with zipfile.ZipFile(zip_path, 'w') as zf:
        zf.writestr('manifest.json', '{"plugin_id": "mismatch", "name": "Mismatch", "version": "1.0.0", "entrypoint": "plugin", "capabilities": [], "permissions": []}')
    
    # Try to install with different plugin_id
    success, msg = pm.install(str(zip_path), 'different_id')
    if not success:
        print('   PASS: Mismatched plugin ID rejected')
    else:
        print('   FAIL: Mismatched plugin ID should be rejected')
        all_passed = False

print()

print('=== CHECKPOINT 12 RESULT: {} ==='.format('PASS' if all_passed else 'FAIL'))

if not all_passed:
    exit(1)