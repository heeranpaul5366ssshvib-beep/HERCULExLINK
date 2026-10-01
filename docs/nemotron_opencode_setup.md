# Nemotron Coding-Agent Setup (OpenCode + Hugging Face Router)

## Config file

`C:\Users\hp\HERCULE\opencode.json` (project-level; takes priority over global config)

Global config checked: `%USERPROFILE%\.config\opencode\opencode.json` — **absent** (no conflict).

## Active OpenCode version

**1.18.31** (`opencode-windows-x64\bin\opencode.exe`; npm shims broken, direct binary used)

## Provider configuration — DONE, verified

```json
{
  "$schema": "https://opencode.ai/config.json",
  "model": "huggingface-nemotron/nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-NVFP4:fireworks-ai",
  "provider": {
    "huggingface-nemotron": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Hugging Face Nemotron",
      "options": {
        "baseURL": "https://router.huggingface.co/v1",
        "apiKey": "{env:HF_TOKEN}"
      },
      "models": {
        "nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-NVFP4:fireworks-ai": {
          "name": "Nemotron 3 Ultra (Fireworks via HF Router)"
        }
      }
    }
  }
}
```

Schema matches the current OpenCode custom-provider pattern
(`npm: @ai-sdk/openai-compatible` + `options.baseURL` + `models` map).
No secret in the file — key resolves from `{env:HF_TOKEN}` at runtime.

## Verification results

| Check | Result |
|---|---|
| JSON syntax | VALID |
| OpenCode discovers project config | YES — `opencode models huggingface-nemotron` lists the model |
| Provider appears | YES |
| Router reachable | YES — `GET /v1/models` returns 200, 136 models |
| Nemotron on router | YES — `nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-NVFP4` listed |
| `HF_TOKEN` present | **NO — absent (also checked HUGGING_FACE_HUB_TOKEN, HUGGINGFACE_TOKEN, HF_API_TOKEN, FIREWORKS_API_KEY, HF cache)** |

## VERIFICATION — ALL GATES PASSED (2026-09-24)

Token supplied in-session (session env only; never written anywhere).

| Gate | Result |
|---|---|
| 1. `HF_TOKEN` present | YES |
| 2. Router inference (`Reply with exactly: HERCULE NEMOTRON TEST OK`) | **HTTP 200**, served model `accounts/fireworks/models/nemotron-3-ultra-nvfp4`, reply exactly `HERCULE NEMOTRON TEST OK` |
| 3. OpenCode selects provider | YES — `opencode run --model huggingface-nemotron/nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-NVFP4:fireworks-ai` executed |
| 4. Coding-agent repo interaction | YES — read `models/hercule_lm/config.py`, correct 3-sentence summary, no files modified |
| 5. No repo modifications | CONFIRMED (`opencode.json` untouched; only this doc updated) |

Chain proven: `C:\Users\hp\HERCULE` → OpenCode → `huggingface-nemotron`
→ `https://router.huggingface.co/v1` → Fireworks → Nemotron 3 Ultra → response.

**SUCCESS declared.** Remaining note: token lives in session env only;
re-set `$env:HF_TOKEN` in each new shell before launching OpenCode.

### To unblock (user action required)

1. Create a token at <https://huggingface.co/settings/tokens> (Inference Providers permission).
2. Set it for the session (never commit it anywhere):
   ```powershell
   $env:HF_TOKEN = "<paste-token-here>"
   ```
3. Run the inference test:
   ```powershell
   cd C:\Users\hp\HERCULE
   & "C:\Users\hp\AppData\Roaming\npm\node_modules\opencode-windows-x64\bin\opencode.exe" run "Reply with exactly: HERCULE NEMOTRON TEST OK" --model huggingface-nemotron/nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-NVFP4:fireworks-ai
   ```
4. Then launch the TUI from `C:\Users\hp\HERCULE` for the read-only repo inspection test.

## Role separation (unchanged)

- Nemotron = coding agent backend only. NOT HERCULE-LM, NOT runtime architecture.
- HERCULE-LM lineage intact: random init → HERCULE data → HERCULE training → HERCULE checkpoints.

## Files changed

- `C:\Users\hp\HERCULE\opencode.json` (created)
- `C:\Users\hp\HERCULE\docs\nemotron_opencode_setup.md` (this file)

No HERCULE source, production state, or unrelated files modified. No secret written anywhere.
