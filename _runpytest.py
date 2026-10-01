import sys, os, traceback
sys.path.insert(0, r'c:\Users\hp\HERCULE')
os.chdir(r'c:\Users\hp\HERCULE')
result_path = r'c:\Users\hp\HERCULE\_smoke.txt'
def write(msg):
    try:
        with open(result_path, 'a', encoding='utf-8') as f:
            f.write(str(msg) + "\n")
    except:
        pass

write("START")
try:
    write("import pytest")
    import pytest
    write("pytest imported OK: " + str(pytest.__version__))
except Exception as e:
    write("IMPORT FAIL: " + str(e))
    write(traceback.format_exc())
    sys.exit(1)

try:
    buf = open(r'c:\Users\hp\HERCULE\_pytest_stdout.txt', 'w')
    err = open(r'c:\Users\hp\HERCULE\_pytest_stderr.txt', 'w')
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = buf
    sys.stderr = err
    exit_code = -999
    try:
        exit_code = pytest.main(['tests/', '-v', '--tb=short',
                                 '-p', 'no:cacheprovider',
                                 '--no-header',
                                 '--override-ini=cache_dir=/tmp/nope'])
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        buf.close()
        err.close()
    write("EXIT: " + str(exit_code))
except Exception as e:
    write("RUN FAIL: " + str(e))
    write(traceback.format_exc())
write("END")
