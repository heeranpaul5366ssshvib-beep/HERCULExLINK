import { useState, useEffect, useCallback } from 'react';

export type AppConfigMap = Record<string, unknown>;

/** Read/write the main-process app config (electron-store). Refreshes periodically. */
export function useAppConfig(pollMs = 10000) {
  const [config, setConfig] = useState<AppConfigMap | null>(null);

  const refresh = useCallback(async () => {
    try {
      if (window.electronAPI) {
        setConfig(await window.electronAPI.config.get());
      }
    } catch {
      // ignore transient IPC errors
    }
  }, []);

  useEffect(() => {
    refresh();
    if (pollMs <= 0) return;
    const id = setInterval(refresh, pollMs);
    return () => clearInterval(id);
  }, [refresh, pollMs]);

  const set = useCallback(
    async (key: string, value: unknown) => {
      if (window.electronAPI) {
        await window.electronAPI.config.set(key, value);
        await refresh();
      }
    },
    [refresh]
  );

  const num = useCallback(
    (key: string, fallback = 0): number => {
      const v = config?.[key];
      return typeof v === 'number' && Number.isFinite(v) ? v : fallback;
    },
    [config]
  );

  return { config, refresh, set, num };
}
