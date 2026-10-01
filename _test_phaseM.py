import sys, os, traceback
sys.path.insert(0, r'c:\Users\hp\HERCULE')
os.chdir(r'c:\Users\hp\HERCULE')
result_path = r'c:\Users\hp\HERCULE\_phaseM.txt'
def write(msg=""):
    try:
        with open(result_path, 'a', encoding='utf-8') as f:
            f.write(str(msg) + "\n")
    except:
        pass

write("=== START Phase M Tests ===")
try:
    import pytest
    write("pytest OK: " + str(pytest.__version__))

    import io
    buf = io.StringIO()
    err_buf = io.StringIO()
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = buf, err_buf
    exit_code = 1
    try:
        exit_code = pytest.main([
            'tests/test_phase_m_semantic.py',
            'tests/test_phase_m_benchmark.py',
            '-v', '--tb=short', '-p', 'no:cacheprovider', '--no-header'
        ])
    finally:
        sys.stdout, sys.stderr = old_out, old_err
    write("EXIT: " + str(exit_code))
    write("\n=== STDOUT ===")
    write(buf.getvalue()[-5000:])
    write("\n=== STDERR ===")
    write(err_buf.getvalue()[-3000:])
except Exception as e:
    write("FAIL: " + str(e))
    write(traceback.format_exc())
write("=== END ===")
