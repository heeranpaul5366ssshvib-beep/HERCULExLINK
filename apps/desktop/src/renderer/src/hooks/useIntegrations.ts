import { useCallback, useEffect, useMemo, useState } from 'react';
import { useLocalStorage } from './useLocalStorage';
import { PLUGINS, TOOLS } from '../data/catalog';
import type { HerculePlugin } from '../types/electron';

export function usePlugins() {
  const [remote, setRemote] = useState<HerculePlugin[] | null>(null);
  const [localEnabled, setLocalEnabled] = useLocalStorage<Record<string, boolean>>('hercule-plugins', {
    github: true,
    web: true,
    vscode: true,
  });

  const refresh = useCallback(async () => {
    try {
      if (window.electronAPI?.plugins) {
        setRemote(await window.electronAPI.plugins.list());
      }
    } catch {
      // fall back to the static catalog
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const toggle = useCallback(
    (id: string) => {
      if (remote) {
        const current = remote.find((p) => p.id === id);
        const next = !(current?.enabled ?? false);
        setRemote((prev) => prev?.map((p) => (p.id === id ? { ...p, enabled: next } : p)) ?? prev);
        window.electronAPI?.plugins?.setEnabled(id, next).then(refresh).catch(refresh);
      } else {
        setLocalEnabled((prev) => ({ ...prev, [id]: !prev[id] }));
      }
    },
    [remote, refresh, setLocalEnabled]
  );

  const plugins = useMemo<HerculePlugin[]>(() => {
    if (remote) return remote;
    return PLUGINS.map((p) => ({
      ...p,
      version: 'built-in',
      permissions: [] as string[],
      source: 'built-in' as const,
      enabled: !!localEnabled[p.id],
    }));
  }, [remote, localEnabled]);

  const connected = useMemo(() => plugins.filter((p) => p.enabled), [plugins]);

  return { plugins, enabled: Object.fromEntries(plugins.map((p) => [p.id, p.enabled])), toggle, connectedCount: connected.length, refresh };
}

export function useTools() {
  const [enabled, setEnabled] = useLocalStorage<Record<string, boolean>>('hercule-tools', {
    'code-runner': true,
    'web-fetch': true,
    'web-search': true,
    'file-search': true,
    calculator: true,
    'task-planner': true,
    memory: true,
  });

  const toggle = useCallback(
    (id: string) => {
      setEnabled((prev) => ({ ...prev, [id]: !prev[id] }));
    },
    [setEnabled]
  );

  const active = useMemo(() => TOOLS.filter((t) => enabled[t.id] !== false), [enabled]);

  return { tools: TOOLS, enabled, toggle, activeCount: active.length };
}
