with open('change_proposals.py', 'r') as f:
    lines = f.readlines()
for i, line in enumerate(lines):
    stripped = line.strip()
    if stripped.startswith('class '):
        class_name = stripped.split()[1].split('(')[0].split(':')[0].strip()
        print(f'Line {i+1}: class {class_name}')