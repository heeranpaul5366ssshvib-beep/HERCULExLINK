# PC-FRONTIER DEPENDENCY INVENTORY

## Environment Summary
- **Python**: 3.14.6 (64-bit)
- **Platform**: Windows 10 (AMD64)
- **Virtual Environment**: C:\Users\hp\HERCULE\.venv
- **pip**: 26.2.1

## Hardware Profile
- **CPU**: Intel Core i3-3220 @ 3.30GHz (2 physical / 4 logical cores)
- **RAM Total**: 8.47 GB
- **RAM Available**: 3.20 GB
- **GPU**: None (CUDA not available)
- **Selected Profile**: LOW

---

## Core Dependencies

| Package | Required? | Installed? | Version | Min Version | Used By | CPU Compatibility | Startup Impact |
|---------|-----------|------------|---------|-------------|---------|-------------------|----------------|
| numpy | ✅ Required | ✅ Yes | 2.5.2 | - | system/hardware, models/*, cognition/*, memory/*, orchestrator/*, benchmark/* | ✅ Compatible | Low |
| psutil | ✅ Required | ✅ Yes | 7.2.2 | - | system/hardware.py | ✅ Compatible | Low |
| pytest | ✅ Required | ✅ Yes | 9.1.1 | - | All tests | ✅ Compatible | N/A (test only) |
| pytest-asyncio | ✅ Required | ✅ Yes | 1.4.0 | - | Async tests | ✅ Compatible | N/A (test only) |
| transformers | ✅ Required | ✅ Yes | 5.16.1 | - | models/hercule_lm/optimized_model.py | ✅ Compatible | Medium |
| torch | ✅ Required | ✅ Yes | 2.14.0+cpu | - | models/hercule_lm/optimized_model.py, system/hardware.py (GPU detection) | ✅ CPU-only | Medium |
| faiss-cpu | ✅ Required | ✅ Yes | 1.15.0 | - | memory/enhanced_memory_manager.py | ✅ Compatible | Low |
| ollama | ⚠️ Optional | ❌ No | - | - | models/router/pc_frontier_router.py (external model fallback) | N/A | N/A |
| sounddevice | ⚠️ Optional | ✅ Yes | 0.5.6 | - | Voice/audio capabilities | ✅ Compatible | Low |
| SpeechRecognition | ⚠️ Optional | ✅ Yes | 3.17.0 | - | Voice/audio capabilities | ✅ Compatible | Low |
| pyttsx3 | ⚠️ Optional | ✅ Yes | Installed (no __version__) | - | Voice/audio capabilities | ✅ Compatible | Low |

---

## Transitive Dependencies (from imports)

| Package | Required? | Installed? | Version | Used By |
|---------|-----------|------------|---------|---------|
| safetensors | ✅ Required | ✅ Yes | 0.8.0 | transformers, models/hercule_lm/optimized_model.py |
| tokenizers | ✅ Required | ✅ Yes | 0.23.2 | transformers |
| huggingface_hub | ✅ Required | ✅ Yes | 1.30.0 | transformers |
| sentence-transformers | ⚠️ Optional | ✅ Yes | 6.0.1 | memory/enhanced_memory_manager.py (embeddings) |
| scikit-learn | ⚠️ Optional | ✅ Yes | 1.9.0 | memory/enhanced_memory_manager.py (clustering) |
| scipy | ✅ Required | ✅ Yes | 1.18.1 | scipy.sparse (faiss), numpy operations |
| networkx | ⚠️ Optional | ✅ Yes | 3.6.1 | cognition/context/enhanced_context_manager.py (graph) |
| rich | ⚠️ Optional | ✅ Yes | 15.0.0 | Logging/output in multiple modules |
| pyyaml | ✅ Required | ✅ Yes | 6.0.3 | Config loading in multiple modules |
| python-dotenv | ⚠️ Optional | ✅ Yes | 1.2.3 | Environment loading |
| httpx | ⚠️ Optional | ✅ Yes | 0.28.1 | External API calls |
| tqdm | ⚠️ Optional | ✅ Yes | 4.70.0 | Progress bars |

---

## Missing Optional Dependencies

| Package | Purpose | Impact |
|---------|---------|--------|
| ollama | External model serving via Ollama | Router will skip Ollama routes, fallback to native/local models only |

---

## Summary

**Status**: PASS - All required dependencies are installed and compatible.

**Optional Missing**: ollama - This is expected for CPU-only environments without Ollama installed.

**Profile Compatibility**: LOW profile selected (3.2 GB available RAM, 4 logical cores, no GPU) - suitable for PC-Frontier operation.

**Torch Backend**: CPU-only (torch 2.14.0+cpu) - CUDA not available, as expected for Intel i3-3220.