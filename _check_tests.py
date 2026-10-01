import sys, os
sys.path.insert(0, r'c:\Users\hp\HERCULE')
os.chdir(r'c:\Users\hp\HERCULE')

import io, contextlib

# Capture stderr too
buf = io.StringIO()
err_buf = io.StringIO()

import pytest

with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err_buf):
    exit_code = pytest.main(['tests/', '-q', '--tb=no', '-p', 'no:cacheprovider', '--no-header'])

combined = "=== STDOUT ===\n" + buf.getvalue() + "\n=== STDERR ===\n" + err_buf.getvalue() + f"\n=== EXIT: {exit_code} ==="

with open(r'c:\Users\hp\HERCULE\_pytest_result.txt', 'w', encoding='utf-8') as f:
    f.write(combined)

# Also print the tail to check
print(combined[-3000:])
