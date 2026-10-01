# PC-FRONTIER RUNTIME BACKEND REPORT

## Torch Backend
- **Version**: 2.14.0+cpu
- **CUDA Available**: False
- **MPS Available**: False
- **CPU Capability**: DEFAULT
- **Build Type**: CPU-only (no CUDA, no MPS)

### dtype Support
| dtype | Supported |
|-------|-----------|
| float32 | ✅ Yes |
| float16 | ✅ Yes |
| bfloat16 | ✅ Yes |
| int8 | ✅ Yes |
| int32 | ✅ Yes |
| int64 | ✅ Yes |

### Basic Operations
- Matrix multiplication: ✅ Working
- Tensor creation: ✅ Working

## NumPy Backend
- **Version**: 2.5.2
- **Platform**: Windows AMD64

## CPU-Only Operation Verification
PC-Frontier can operate on CPU-only hardware:
- ✅ Torch CPU backend functional
- ✅ All required dtypes supported (including float16/bfloat16 for quantization)
- ✅ No CUDA dependencies in core path
- ✅ Quantization (int8) supported for LOW/ULTRA_LOW profiles

## Checkpoint 5 Gate
**PASS** - Runtime backend capabilities are known. CPU-only operation verified with full dtype support including quantization-friendly types (float16, bfloat16, int8).