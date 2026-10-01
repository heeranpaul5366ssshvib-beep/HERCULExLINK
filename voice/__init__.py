"""Voice interaction subsystem (v1.1 upgrade layer).

Interface only: microphone -> STT -> existing HERCULE request pipeline
(Brain) -> response -> TTS. Voice is never a second Brain: transcripts
enter through the same controller.submit() path as typed input.
"""
