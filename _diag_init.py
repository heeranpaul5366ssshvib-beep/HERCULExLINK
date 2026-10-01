"""Diagnostic: test RuntimeInitializer imports step by step."""
import sys, traceback

RESULT = r"c:\Users\hp\HERCULE\_diag_init.txt"
def log(msg):
    with open(RESULT, "a", encoding="utf-8") as f:
        f.write(msg + "\n"); f.flush()
    print(msg)

if __name__ == "__main__":
    with open(RESULT, "w", encoding="utf-8") as f:
        f.write("=== RuntimeInitializer Diagnostic ===\n")
    sys.path.insert(0, r"c:\Users\hp\HERCULE")
    try:
        log("1. Importing RuntimeInitializer...")
        from runtime.initializer import RuntimeInitializer
        log("   OK")
        log("2. Instantiating...")
        ri = RuntimeInitializer()
        log("   OK")
        log("3. Calling initialize()...")
        services = ri.initialize()
        log(f"   OK: keys = {list(services.keys())}")
        brain = services["brain"]
        log(f"   OK: brain = {type(brain).__name__}")
        log(f"   OK: brain.orchestrator = {type(brain.orchestrator).__name__}")
        log(f"   OK: brain.authoritative_planner = {type(brain.authoritative_planner).__name__}")
        log("\n=== DIAG PASSED ===")
    except Exception as e:
        log(f"FAIL: {e}")
        log(traceback.format_exc())
        sys.exit(1)
