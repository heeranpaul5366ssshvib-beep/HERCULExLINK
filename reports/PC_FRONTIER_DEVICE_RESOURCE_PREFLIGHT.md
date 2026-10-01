# PC-FRONTIER DEVICE/RESOURCE PREFLIGHT REPORT

## Hardware Detection Results

### System Information
- **Platform**: Windows 10 (AMD64)
- **Python**: 3.14.6
- **Timestamp**: 2026-09-27T14:13:01.172987+00:00

### CPU
- **Model**: Intel(R) Core(TM) i3-3220 CPU @ 3.30GHz
- **Physical Cores**: 2
- **Logical Cores**: 4
- **Max Frequency**: 3300 MHz
- **Architecture**: AMD64

### Memory
- **Total**: 8472 MB (8.27 GB)
- **Available**: 3204 MB (3.13 GB)
- **Free**: 3204 MB
- **Used**: 5268 MB
- **Percent Used**: 62.2%

### GPU
- **CUDA Available**: No
- **Device Count**: 0
- **Total VRAM**: 0 MB
- **Primary Device**: NONE

### Disk
- **Free**: 37090 MB (36.2 GB)

## Profile Selection

### Selected Profile: **LOW**

### Profile Selection Logic
- GPU with sufficient VRAM: No (CUDA not available)
- Available RAM: 3204 MB >= 2000 MB ✓
- CPU Cores: 4 >= 2 ✓
- Result: LOW profile (ram_mb >= 2000 and cores >= 2)

### Profile Configuration (LOW)
| Parameter | Value |
|-----------|-------|
| max_model_params | 50,000,000 (50M) |
| max_context_tokens | 2048 |
| batch_size | 1 |
| num_threads | 2 |
| use_kv_cache | True |
| use_quantization | True |
| enable_streaming | True |
| prefer_native_lm | True |
| allow_external_models | True |
| memory_limit_mb | 1024 |
| verification_required | True |

## Checkpoint 4 Gate
**PASS** - Hardware detection is internally consistent. Profile selection logic correctly identifies LOW profile for this hardware configuration (3.2 GB available RAM, 4 logical cores, no GPU).