# Issue 003 — ASR & TTS Pipeline (Speech)

Priority: Medium
Estimate: 2–4 person-weeks

Goal
- Provide pluggable ASR and TTS adapters for conversational voice I/O.

Acceptance criteria
- A `perception/speech` adapter interface and at least one working ASR/TTS backend (e.g., Vosk for ASR, pyttsx3 for TTS) for offline/local usage.
- Demonstration script that records microphone input, sends to ASR, runs a simple agent response, and speaks via TTS.

Files to change (suggested)
- `perception/speech/` — add adapters and manager
- `communication/` — add voice input/output hooks
