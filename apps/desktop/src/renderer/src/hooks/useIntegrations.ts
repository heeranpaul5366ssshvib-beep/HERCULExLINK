import { useCallback, useMemo } from 'react';
import { useLocalStorage } from './useLocalStorage';
import { PLUGINS, TOOLS } from '../data/catalog';

export function usePlugins() {
  const [enabled, setEnabled] = useLocalStorage<Record<string, boolean>>('hercule-plugins', {
    github: true,
    web: true,
    vscode: true,
  });

  const toggle = useCallback(
    (id: string) => {
      setEnabled((prev) => ({ ...prev, [id]: !prev[id] }));
    },
    [setEnabled]
  );

  const connected = useMemo(() => PLUGINS.filter((p) => enabled[p.id]), [enabled]);

  return { plugins: PLUGINS, enabled, toggle, connectedCount: connected.length };
}

export function useTools() {
  const [enabled, setEnabled] = useLocalStorage<Record<string, boolean>>('hercule-tools', {
    'code-runner': true,
    'web-fetch': true,
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
