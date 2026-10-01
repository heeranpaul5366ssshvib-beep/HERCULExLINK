import sys, os

RESULT = r"c:\Users\hp\HERCULE\_diag_min.txt"

with open(RESULT, "w", encoding="utf-8") as f:
    f.write("START\n")
    f.write(f"CWD={os.getcwd()}\n")
    f.write(f"PYTHON={sys.executable}\n")
    f.flush()

sys.path.insert(0, r"c:\Users\hp\HERCULE")

with open(RESULT, "a", encoding="utf-8") as f:
    f.write("after path insert\n"); f.flush()

try:
    from runtime.initializer import RuntimeInitializer
    with open(RESULT, "a", encoding="utf-8") as f:
        f.write("imported RI ok\n"); f.flush()
except Exception as e:
    with open(RESULT, "a", encoding="utf-8") as f:
        f.write(f"RI import FAIL: {e}\n"); f.flush()
    raise
