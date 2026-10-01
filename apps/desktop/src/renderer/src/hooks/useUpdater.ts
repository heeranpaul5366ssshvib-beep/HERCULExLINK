import { useState, useEffect, useCallback } from 'react';

type UpdaterStatus = 'idle' | 'checking' | 'available' | 'not-available' | 'downloading' | 'downloaded' | 'error';

export function useUpdater() {
  const [status, setStatus] = useState<UpdaterStatus>('idle');
  const [version, setVersion] = useState<string>('');
  const [progress, setProgress] = useState<{ percent: number; transferred: number; total: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!window.electronAPI) return;

    const VALID_STATUSES: UpdaterStatus[] = ['idle', 'checking', 'available', 'not-available', 'downloading', 'downloaded', 'error'];
    const unsubscribeStatus = window.electronAPI.updater.onStatus((updateStatus) => {
      if (VALID_STATUSES.includes(updateStatus.status as UpdaterStatus)) {
        setStatus(updateStatus.status as UpdaterStatus);
      }
      if (updateStatus.version) setVersion(updateStatus.version);
      if (updateStatus.error) setError(updateStatus.error);
    });

    const unsubscribeProgress = window.electronAPI.updater.onProgress((prog) => {
      setProgress(prog);
    });

    return () => {
      unsubscribeStatus();
      unsubscribeProgress();
    };
  }, []);

  const checkForUpdates = useCallback(async () => {
    setStatus('checking');
    setError(null);
    try {
      if (window.electronAPI) {
        await window.electronAPI.updater.check();
      } else {
        setStatus('not-available');
      }
    } catch (err) {
      setStatus('error');
      setError(err instanceof Error ? err.message : 'Update check failed');
    }
  }, []);

  const installUpdate = useCallback(async () => {
    try {
      if (window.electronAPI) {
        await window.electronAPI.updater.install();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Update install failed');
    }
  }, []);

  return { status, version, progress, error, checkForUpdates, installUpdate };
}