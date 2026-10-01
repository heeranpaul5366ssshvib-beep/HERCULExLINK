from security.sandbox.sandbox_manager import SandboxManager, SandboxProfile, SandboxLimits

sm = SandboxManager()
print('Status:', sm.status())

# Test simple command using python -c
result = sm.execute(['python', '-c', 'print("hello world")'], profile=SandboxProfile.STRICT)
print('Echo result:', result.exit_code, result.stdout.strip())

# Test with timeout
result = sm.execute(['python', '-c', 'import time; time.sleep(2)'], profile=SandboxProfile.STRICT, timeout=1)
print('Timeout result:', result.exit_code, result.timed_out)