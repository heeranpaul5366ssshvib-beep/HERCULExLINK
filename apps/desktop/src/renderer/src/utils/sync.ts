// v2.6 renderer side: push desktop workspace to main, merge phone updates in.
import type { HerculeSyncPush } from '../types/electron';

interface Syncable {
  id: string;
  updatedAt?: number;
  createdAt?: number;
}

function readArr(key: string): Syncable[] {
  try {
    const raw = localStorage.getItem(key);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? (parsed as Syncable[]).slice(0, 2000) : [];
  } catch {
    return [];
  }
}

function stampOf(item: Syncable): number {
  if (typeof item.updatedAt === 'number') return item.updatedAt;
  if (typeof item.createdAt === 'number') return item.createdAt;
  return 0;
}

export function collectSnapshot(): HerculeSyncPush {
  let goal = '';
  try {
    goal = JSON.parse(localStorage.getItem('hercule-autonomy-goal') ?? '""') as string;
    if (typeof goal !== 'string') goal = '';
  } catch {
    goal = '';
  }
  return {
    tasks: readArr('hercule-tasks'),
    projects: readArr('hercule-projects'),
    memories: readArr('hercule-memories'),
    goal,
    goalUpdatedAt: Date.now(),
  };
}

function mergeArr(key: string, incoming: unknown): boolean {
  if (!Array.isArray(incoming)) return false;
  const map = new Map<string, Syncable>();
  for (const item of readArr(key)) {
    if (item && typeof item.id === 'string') map.set(item.id, item);
  }
  let changed = false;
  for (const raw of (incoming as unknown[]).slice(0, 2000)) {
    const item = raw as Syncable;
    if (!item || typeof item.id !== 'string') continue;
    const prev = map.get(item.id);
    if (!prev || stampOf(item) >= stampOf(prev)) {
      if (!prev || JSON.stringify(prev) !== JSON.stringify(item)) changed = true;
      map.set(item.id, item);
    }
  }
  if (!changed) return false;
  try {
    localStorage.setItem(key, JSON.stringify([...map.values()].slice(0, 2000)));
  } catch {
    return false;
  }
  return true;
}

/** Merge a phone snapshot into localStorage. Returns keys that changed. */
export function mergeIncoming(snap: Record<string, unknown>): string[] {
  const changed: string[] = [];
  const pairs: Array<[string, unknown]> = [
    ['hercule-tasks', snap.tasks],
    ['hercule-projects', snap.projects],
    ['hercule-memories', snap.memories],
  ];
  for (const [key, value] of pairs) {
    if (mergeArr(key, value)) changed.push(key);
  }
  if (typeof snap.goal === 'string' && typeof snap.goalUpdatedAt === 'number') {
    try {
      const current = localStorage.getItem('hercule-autonomy-goal');
      if (current !== JSON.stringify(snap.goal)) {
        localStorage.setItem('hercule-autonomy-goal', JSON.stringify(snap.goal.slice(0, 500)));
        changed.push('hercule-autonomy-goal');
      }
    } catch {
      // ignore
    }
  }
  if (changed.length > 0) {
    window.dispatchEvent(new CustomEvent('hercule:storage-changed', { detail: '*' }));
  }
  return changed;
}
