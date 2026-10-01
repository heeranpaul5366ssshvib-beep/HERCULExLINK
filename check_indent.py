with open('workspace_manager.py', 'rb') as f:
    content = f.read()
idx = content.find(b'def _record_access')
if idx >= 0:
    start = max(0, idx - 80)
    segment = content[start:idx+80]
    for i, b in enumerate(segment):
        print(f'{i:3d}: {b:3d} {chr(b) if 32 <= b < 127 else "."}')