import { useState, useEffect, useCallback } from 'react';

export interface InstallerStatus {
  firstRun: boolean;
  modelInstalled: boolean;
  modelPath: string;
  shortcutsCreated: boolean;
  autoStartEnabled: boolean;
  telemetryOptIn: boolean | null;
}

export interface InstallerProgress {
  stage: string;
  progress: number;
  message: string;
}

export function useInstaller() {
  const [status, setStatus] = useState<InstallerStatus | null>(null);
  const [progress, setProgress] = useState<InstallerProgress | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const fetchStatus = useCallback(async () => {
    try {
      if (window.electronAPI) {
        const installerStatus = await window.electronAPI.installer.getStatus();
        setStatus(installerStatus);
      }
    } catch (err) {
      console.error('Failed to fetch installer status:', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();

    if (!window.electronAPI) return;
    const unsubscribe = window.electronAPI.installer.onProgress((newProgress: InstallerProgress) => {
      setProgress(newProgress);
    });
    return unsubscribe;
  }, [fetchStatus]);

  const reset = useCallback(async () => {
    try {
      if (window.electronAPI) {
        await window.electronAPI.installer.reset();
        fetchStatus();
      }
    } catch (err) {
      console.error('Failed to reset installer:', err);
    }
  }, [fetchStatus]);

  const runSetup = useCallback(async () => {
    try {
      if (window.electronAPI) {
        setProgress({ stage: 'starting', progress: 0, message: 'Starting setup...' });
        await window.electronAPI.installer.runSetup();
        fetchStatus();
      }
    } catch (err) {
      console.error('Failed to run setup:', err);
      setProgress(null);
    }
  }, [fetchStatus]);

  return {
    status,
    progress,
    isLoading,
    fetchStatus,
    reset,
    runSetup,
  };
}