import { useState, useCallback } from 'react';

type ModelStatus = 'not-installed' | 'installing' | 'installed' | 'starting' | 'running' | 'stopped' | 'error';

export function useModelStatus() {
  const [status, setStatus] = useState<ModelStatus>('not-installed');
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [port, setPort] = useState<number | null>(null);

  const installModel = useCallback(async (url: string) => {
    setStatus('installing');
    setProgress(0);
    setError(null);

    try {
      if (window.electronAPI) {
        const modelPath = await window.electronAPI.model.install(url);
        setStatus('installed');
        return modelPath;
      } else {
        for (let i = 0; i <= 100; i += 10) {
          await new Promise(r => setTimeout(r, 100));
          setProgress(i);
        }
        setStatus('installed');
        return '/mock/path/model.gguf';
      }
    } catch (err) {
      setStatus('error');
      setError(err instanceof Error ? err.message : 'Installation failed');
      throw err;
    }
  }, []);

  const startModel = useCallback(async () => {
    setStatus('starting');
    setError(null);
    try {
      if (window.electronAPI) {
        const result = await window.electronAPI.model.start();
        setPort(result.port);
        setStatus('running');
        return result;
      } else {
        await new Promise(r => setTimeout(r, 2000));
        setPort(8765);
        setStatus('running');
        return { port: 8765, pid: 1234 };
      }
    } catch (err) {
      setStatus('error');
      setError(err instanceof Error ? err.message : 'Failed to start model');
      throw err;
    }
  }, []);

  const stopModel = useCallback(async () => {
    setStatus('stopped');
    setPort(null);
    try {
      if (window.electronAPI) {
        await window.electronAPI.model.stop();
      }
    } catch (err) {
      console.error('Failed to stop model:', err);
    }
  }, []);

  return { status, progress, error, port, installModel, startModel, stopModel };
}