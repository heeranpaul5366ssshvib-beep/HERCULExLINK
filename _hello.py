import os
p = r'c:\Users\hp\HERCULE\_hello.txt'
try:
    with open(p, 'w') as f:
        f.write(f'Hello from Python\nCWD={os.getcwd()}\n')
    print('WROTE:', os.path.exists(p), p)
except Exception as e:
    print('ERROR:', e)
