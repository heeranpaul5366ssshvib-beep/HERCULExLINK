with open('C:/Users/hp/HERCULE/change_proposal_manager.py', 'rb') as f:
    content = f.read()
idx = content.find(b'def _build_create_proposal')
if idx >= 0:
    start = max(0, idx - 50)
    end = idx + 200
    segment = content[start:idx+200]
    for i, b in enumerate(segment):
        if b in (9, 10, 13, 32):
            label = "TAB" if b==9 else "LF" if b==10 else "CR" if b==13 else "SP"
            print(f'{i:3d}: {b:3d} {label}')