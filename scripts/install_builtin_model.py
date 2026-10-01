from __future__ import annotations
"""Install the built-in local model (Mode B: separate model package).

Downloads the managed llama.cpp runtime (when missing) and a curated
GGUF model into %LOCALAPPDATA%\\HERCULE\\models. No API keys, no
Ollama required. Usage:
    python scripts/install_builtin_model.py [model-id]
Default model: qwen2.5-0.5b-q4 (small, CPU-friendly).
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


def main() -> int:
    from models.builtin import model_manager as store

    model_id = sys.argv[1] if len(sys.argv) > 1 else "qwen2.5-0.5b-q4"
    print(f"model store: {store.models_root()}")
    try:
        runtime = store.ensure_runtime()
        print(f"runtime ready: {runtime}")
    except Exception as exc:
        print(f"runtime setup failed: {exc}")
        return 1
    try:
        receipt = store.download_model(model_id)
    except Exception as exc:
        print(f"model download failed: {exc}")
        return 1
    print(f"model ready: {receipt['id']} ({receipt['size']} bytes)"
          + (" [cached]" if receipt.get("cached") else ""))
    try:
        selected = store.select_default(receipt["id"])
        print(f"default model: {selected}")
    except Exception as exc:
        print(f"select-default note: {exc}")
    for meta in store.list_installed():
        print(f"  installed: {meta['id']} {meta['size']} bytes {meta['path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
