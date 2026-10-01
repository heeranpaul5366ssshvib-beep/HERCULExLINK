import { useState, useEffect, useCallback } from 'react';

const STORAGE_EVENT = 'hercule:storage-changed';

function readValue<T>(key: string, initialValue: T): T {
  try {
    const raw = localStorage.getItem(key);
    if (raw === null) return initialValue;
    return JSON.parse(raw) as T;
  } catch {
    return initialValue;
  }
}

/**
 * useState persisted to localStorage, synced across hooks/components
 * in the same window via a custom event.
 */
export function useLocalStorage<T>(key: string, initialValue: T) {
  const [value, setValue] = useState<T>(() => readValue(key, initialValue));

  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<string>).detail;
      if (detail === key || detail === '*') {
        setValue(readValue(key, initialValue));
      }
    };
    window.addEventListener(STORAGE_EVENT, handler);
    return () => window.removeEventListener(STORAGE_EVENT, handler);
  }, [key, initialValue]);

  const set = useCallback(
    (next: T | ((prev: T) => T)) => {
      setValue((prev) => {
        const resolved = typeof next === 'function' ? (next as (p: T) => T)(prev) : next;
        try {
          localStorage.setItem(key, JSON.stringify(resolved));
        } catch {
          // Storage full or unavailable; keep in-memory state.
        }
        window.dispatchEvent(new CustomEvent(STORAGE_EVENT, { detail: key }));
        return resolved;
      });
    },
    [key]
  );

  return [value, set] as const;
}

export function clearHerculeStorage(keys: string[]) {
  for (const key of keys) {
    try {
      localStorage.removeItem(key);
    } catch {
      // ignore
    }
  }
  window.dispatchEvent(new CustomEvent(STORAGE_EVENT, { detail: '*' }));
}
