# Phase N2 — Built-in local LLM provider

Date: 2026-09-20 — Status: accepted (measured, not ranked)

## Context

HERCULE shipped with one bundled GGUF model (Qwen2.5 0.5B, chat-only
profile) while the reasoning controller's DEEP/EXPERT heuristics
preferred whatever Ollama model looked biggest or "thinking-capable"
— including a degraded one (see N1 routing audit). Normal operation
should not require an Ollama server.

## Decision

- Second bundled-class model: **Qwen2.5-1.5B-Instruct-Q4_K_M**
  (Apache-2.0; weights live in `%LOCALAPPDATA%\HERCULE\models\gguf\`,
  never in the repo). On this machine the weights were sourced from
  the locally installed Ollama `qwen2.5:1.5b` blob store (same
  weights, verified by manifest digest + GGUF magic) because the
  network path to HuggingFace cannot sustain large transfers here.
  Canonical source remains
  `bartowski/Qwen2.5-1.5B-Instruct-GGUF` via `download_model()`.
- Hardware floor observed: 2C/4T Ivy Bridge CPU, ~4 GB free RAM.
  A 3B model fits but leaves little headroom; 1.5B (≈1 GB) is the
  responsible primary on this class of machine.
- Catalog entries carry license/family/parameters/recommended-modes;
  `list_installed()` enriches discovered weights from the catalog.
- Controller inventory grants the `reasoning` profile to installed
  built-in models ≥ 1 GB; smaller ones stay chat/classification.
- `HERCULE_MODEL_PROVIDER=builtin` restricts routing to built-in
  models (existing mechanism); `ollama` value keeps Ollama-only;
  `auto` keeps legacy heuristics. Explicit user configuration always
  wins over defaults.
- Production default is unchanged (`auto`) pending Step-35
  acceptance; local-first is opt-in via configuration until then.
- `BuiltinLocalProvider.health()` reports the actually-loaded model
  id (previously re-resolved via config and could misreport).

## Consequences

- Offline operation verified: conversation + tasks work with Ollama
  unreachable and no network (Step 10/11 acceptance).
- Absence is honest: no GGUF + no Ollama yields a clear
  MODEL NOT INSTALLED error, never silent mock (Step 12).
- Deterministic tasks never needed a model and still don't.
- Installer strategy unchanged: weights stay out of the bundle
  (`hercule.iss` excludes model weights); user-data acquisition only.
