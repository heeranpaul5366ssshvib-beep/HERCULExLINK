import sys, os, traceback
sys.path.insert(0, r'c:\Users\hp\HERCULE')
os.chdir(r'c:\Users\hp\HERCULE')
p = r'c:\Users\hp\HERCULE\_debug.txt'
with open(p, 'w', encoding='utf-8') as f:
    def W(m=""):
        f.write(str(m)+"\n"); f.flush()
    try:
        from system.config.semantic_config import load_semantic_config
        W("imported")
        config = load_semantic_config({}, env={})
        W(f"config.enabled={config.enabled} type={type(config.enabled)}")
        W(f"config.min_confidence={config.min_confidence} type={type(config.min_confidence)}")
        W(f"config.enabled is False -> {config.enabled is False}")
        W(f"bool(config.enabled) -> {bool(config.enabled)}")
        env_config = load_semantic_config({}, env={
            "HERCULE_SEMANTIC_ENABLED": "true",
            "HERCULE_SEMANTIC_MODE": "shadow",
            "HERCULE_SEMANTIC_CONFIDENCE": "0.7",
        })
        W(f"env_config.enabled={env_config.enabled} -> {type(env_config.enabled)}")
        W(f"env_config.shadow={env_config.shadow}")
        W(f"env_config.min_confidence={env_config.min_confidence}")
    except Exception as e:
        W(f"FAIL: {e}")
        W(traceback.format_exc())
print("done")
