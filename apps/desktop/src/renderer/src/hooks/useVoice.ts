import { useState, useEffect, useRef, useCallback } from 'react';
import { useLocalStorage } from './useLocalStorage';

// v2.4: voice mode. Speech output (speechSynthesis) runs fully on-device via
// OS voices. Speech input uses the browser recognition service when present
// (needs internet) — the UI labels this honestly and disables the mic where
// the build has no recognition backend (e.g. packaged Electron without one).

/** Strip markdown/code so the speaker reads words, not syntax. */
export function cleanTextForSpeech(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, ' code block omitted ')
    .replace(/`([^`]*)`/g, '$1')
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/[*_~]{1,3}/g, '')
    .replace(/^>\s?/gm, '')
    .replace(/https?:\/\/\S+/g, 'link')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 2000);
}

interface SpeechRecognitionLike extends EventTarget {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}

function getRecognizer(): (new () => SpeechRecognitionLike) | null {
  if (typeof window === 'undefined') return null;
  const w = window as unknown as Record<string, unknown>;
  const ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition;
  return typeof ctor === 'function' ? (ctor as new () => SpeechRecognitionLike) : null;
}

export function useVoice() {
  const [voiceOn, setVoiceOn] = useLocalStorage<boolean>('hercule-voice-reply', false);
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const recogRef = useRef<SpeechRecognitionLike | null>(null);

  const supportedSTT = getRecognizer() !== null;
  const supportedTTS =
    typeof window !== 'undefined' && typeof window.speechSynthesis !== 'undefined';

  useEffect(() => {
    return () => {
      try {
        recogRef.current?.abort();
      } catch {
        // ignore
      }
      try {
        window.speechSynthesis?.cancel();
      } catch {
        // ignore
      }
    };
  }, []);

  const stopListening = useCallback(() => {
    try {
      recogRef.current?.stop();
    } catch {
      // ignore
    }
    recogRef.current = null;
    setListening(false);
  }, []);

  const startListening = useCallback(
    (onTranscript: (text: string, final: boolean) => void) => {
      const Ctor = getRecognizer();
      if (!Ctor) {
        setVoiceError('Voice input is not available in this build.');
        return;
      }
      try {
        recogRef.current?.abort();
      } catch {
        // ignore
      }
      setVoiceError(null);
      const recog = new Ctor();
      recogRef.current = recog;
      recog.lang = 'en-US';
      recog.interimResults = true;
      recog.continuous = false;
      recog.onresult = (e) => {
        let interim = '';
        let finalText = '';
        for (let i = 0; i < e.results.length; i++) {
          const res = e.results[i];
          if (!res) continue;
          const alt = res[0];
          if (!alt) continue;
          if ((res as unknown as { isFinal?: boolean }).isFinal) finalText += alt.transcript;
          else interim += alt.transcript;
        }
        if (finalText) onTranscript(finalText, true);
        else if (interim) onTranscript(interim, false);
      };
      recog.onerror = (e) => {
        setListening(false);
        recogRef.current = null;
        if (e.error === 'not-allowed' || e.error === 'service-not-allowed') {
          setVoiceError('Microphone blocked — allow it, then try again.');
        } else if (e.error === 'network') {
          setVoiceError('Voice input needs internet (browser service).');
        } else if (e.error !== 'aborted' && e.error !== 'no-speech') {
          setVoiceError(`Voice input error: ${e.error}`);
        }
      };
      recog.onend = () => {
        setListening(false);
        recogRef.current = null;
      };
      try {
        recog.start();
        setListening(true);
      } catch {
        setVoiceError('Could not start voice input.');
      }
    },
    []
  );

  const stopSpeaking = useCallback(() => {
    try {
      window.speechSynthesis?.cancel();
    } catch {
      // ignore
    }
    setSpeaking(false);
  }, []);

  const speak = useCallback(
    (text: string) => {
      if (!supportedTTS) return;
      try {
        window.speechSynthesis.cancel();
        const cleaned = cleanTextForSpeech(text);
        if (!cleaned) return;
        const utter = new SpeechSynthesisUtterance(cleaned);
        utter.rate = 1;
        utter.onend = () => setSpeaking(false);
        utter.onerror = () => setSpeaking(false);
        setSpeaking(true);
        window.speechSynthesis.speak(utter);
      } catch {
        setSpeaking(false);
      }
    },
    [supportedTTS]
  );

  return {
    voiceOn,
    setVoiceOn,
    listening,
    speaking,
    voiceError,
    supportedSTT,
    supportedTTS,
    startListening,
    stopListening,
    speak,
    stopSpeaking,
  };
}
