from security.sandbox.sandbox_manager import SandboxManager, SandboxProfile, SandboxLimits

sm = SandboxManager()
print('Status:', sm.status())

# Test network profile (allows network)
result = sm.execute(['python', '-c', 'import urllib.request; print(urllib.request.urlopen("http://httpbin.org/get").read()[:50])'], profile=SandboxProfile.NETWORK, timeout=10)
print('Network result:', result.exit_code, result.stdout[:100] if result.stdout else '')

# Test filesystem profile with workspace access
result = sm.execute(['python', '-c', 'open("test_sandbox_write.txt", "w").write("hello from sandbox"); print("written")'], profile=SandboxProfile.FILESYSTEM)
print('Filesystem write:', result.exit_code, result.stdout.strip())

# Check file was created
import os
print('File exists:', os.path.exists('test_sandbox_write.txt'))
if os.path.exists('test_sandbox_write.txt'):
    with open('test_sandbox_write.txt') as f:
        print('Content:', f.read())
    os.unlink('test_sandbox_write.txt')

# Test active sandboxes tracking
print('Active sandboxes:', sm.get_active_sandboxes())