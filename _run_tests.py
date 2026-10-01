import subprocess
r = subprocess.run(
    [r'.venv\Scripts\python.exe', '-m', 'pytest', 'tests/', '-q', '--tb=no'],
    capture_output=True, text=True, cwd=r'c:\Users\hp\HERCULE'
)
with open(r'c:\Users\hp\HERCULE\_test_result.txt', 'w') as f:
    f.write('=== STDOUT ===\n')
    f.write(r.stdout)
    f.write('\n=== STDERR ===\n')
    f.write(r.stderr)
    f.write(f'\n=== EXIT CODE: {r.returncode} ===\n')
print('DONE. exit=', r.returncode)
print('stdout tail:', r.stdout[-1500:])
