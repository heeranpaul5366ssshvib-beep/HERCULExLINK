# HERCULE v1.0.0 — Release Notes

**HERCULE AI Operating System — Version 1.0.0**

## What is HERCULE

HERCULE is a modular AI operating system that runs local large language
models (Ollama, API-key-free) through a Brain → planner → policy-gated
abilities → verification pipeline, with persistent memory, experience
learning, background autonomy, a tkinter desktop UI with HUD overlay,
and a CLI/headless mode.

## v1.0.0 highlights

- Canonical runtime: Brain, Consciousness (explicit lifecycle states),
  hybrid deterministic/cognitive planner, AutonomousLoop, AutonomyWorker.
- Real local Ollama integration: dynamic model discovery, honest
  model-unavailable errors, mock adapter excluded from production.
- 17 default abilities (math, files, diagnostics, terminal allowlist,
  …) behind capability validation → permission policy → verification.
- Persistent memory (episodic/semantic/procedural/vector) with retention
  caps, dedup, corruption recovery; experience lessons only from
  verified outcomes.
- Durable tasks: atomic writes, malformed-entry tolerance, restart
  recovery without replaying verified steps.
- Desktop UI + HUD (read-only visualization), `/health` diagnostics,
  clean shutdown everywhere.
- Windows installer (`HERCULE-Setup.exe`): Program Files install, Start
  Menu + optional Desktop shortcuts, uninstaller; user data stays in
  `%LOCALAPPDATA%\HERCULE` and survives upgrade/uninstall.

## Install

1. Install Ollama separately and pull a model (`ollama pull llama3.2:3b`).
2. Run `HERCULE-Setup.exe`, launch from the Start Menu.
3. No Python environment needed; no model weights are bundled.

## Verification (this release)

- `python -m pytest`: 460 passed, 9 skipped, 2 failed — both failures
  are environment-sensitive and unrelated to backend correctness (broken
  venv `torch` C-extension; one test assumes Ollama is unreachable).
- Production exe verified: conversation, identity, calculation, system
  diagnostics, file create/read, multi-step task, verification,
  honest failure/recovery, memory persistence, restart recovery,
  clean shutdown.
- Clean install verified: install → launch → UI → ability → persistence
  → shutdown → uninstall → user data preserved.

## Known limitations

- Local CPU inference latency dominates (seconds per model call);
  deterministic requests skip the LLM.
- Single-utterance anaphoric references ("read it back") may fail plan
  contract validation honestly instead of executing; explicit phrasing
  works.
- `torch`/transformers stacks are excluded from the installer and the
  sentence-transformers embedding backend is unavailable when its
  weights/native libs are missing (hash embeddings apply).
- Consciousness states describe runtime lifecycle position only; they
  are not a claim of sentience.
