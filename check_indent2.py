with open('workspace_manager.py', 'rb') as f:
    content = f.read()
idx = content.find(b'def _record_access')
if idx >= 0:
    start = max(0, idx - 100)
    segment = content[start:idx+100]
    for i, b in enumerate(segment):
        if b in (9, 10, 13, 32):
            label = "TAB" if b==9 else "LF" if b==10 else "CR" if b==13 else "SP"
            print(f'{i:3d}: {b:3d} {label}')