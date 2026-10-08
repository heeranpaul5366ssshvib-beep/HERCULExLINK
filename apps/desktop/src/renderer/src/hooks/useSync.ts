import { useState, useEffect, useCallback, useRef } from 'react';
import type { HerculeSyncInfo } from '../types/electron';
import { collectSnapshot, mergeIncoming } from '../utils/sync';

const EMPTY: HerculeSyncInfo = {
  enabled: false, addresses: [], port: 8766, pairingCode: '', paired: false, lastSyncAt: 0,
};

export function useSync() {
  const [info, setInfo] = useState<HerculeSyncInfo>(EMPTY);
  const [busy, setBusy] = useState(false);
  const pushTimer = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    try {
      if (window.electronAPI?.sync) setInfo(await window.electronAPI.sync.info());
    } catch {
      // sync unavailable (web preview)
    }
  }, []);

  const push = useCallback(async () => {
    try {
      if (window.electronAPI?.sync) await window.electronAPI.sync.push(collectSnapshot());
    } catch {
      // never break the UI for sync
    }
  }, []);

  const pullMerge = useCallback(async () => {
    try {
      if (!window.electronAPI?.sync) return;
      const snap = (await window.electronAPI.sync.pull()) as Record<string, unknown>;
      mergeIncoming(snap ?? {});
      await refresh();
    } catch {
      // ignore
    }
  }, [refresh]);

  // Keep main's copy fresh: push (debounced) whenever workspace changes.
  useEffect(() => {
    const handler = () => {
      if (pushTimer.current) window.clearTimeout(pushTimer.current);
      pushTimer.current = window.setTimeout(() => {
        void (async () => {
          try {
            const current = window.electronAPI?.sync ? await window.electronAPI.sync.info() : null;
            if (current?.enabled) await push();
          } catch {
            // ignore
          }
        })();
      }, 2000);
    };
    window.addEventListener('hercule:storage-changed', handler);
    return () => {
      window.removeEventListener('hercule:storage-changed', handler);
      if (pushTimer.current) window.clearTimeout(pushTimer.current);
    };
  }, [push]);

  // Phone wrote something: merge it in.
  useEffect(() => {
    if (!window.electronAPI?.sync) return;
    const off = window.electronAPI.sync.onUpdated(() => {
      void pullMerge();
    });
    return off;
  }, [pullMerge]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const setEnabled = useCallback(
    async (on: boolean) => {
      setBusy(true);
      try {
        if (window.electronAPI?.sync) {
          await window.electronAPI.sync.setEnabled(on);
          if (on) await push();
          await refresh();
        }
      } finally {
        setBusy(false);
      }
    },
    [push, refresh]
  );

  const rotateCode = useCallback(async () => {
    try {
      if (window.electronAPI?.sync) {
        await window.electronAPI.sync.rotateCode();
        await refresh();
      }
    } catch {
      // ignore
    }
  }, [refresh]);

  const unpair = useCallback(async () => {
    try {
      if (window.electronAPI?.sync) {
        await window.electronAPI.sync.unpair();
        await refresh();
      }
    } catch {
      // ignore
    }
  }, [refresh]);

  return { info, busy, refresh, setEnabled, rotateCode, unpair };
}
