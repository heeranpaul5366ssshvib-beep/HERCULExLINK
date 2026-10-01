import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

export type AccentName = 'blue' | 'violet' | 'emerald' | 'amber';
export type FontScale = 'compact' | 'regular' | 'large';

export const ACCENTS: Record<AccentName, { label: string; main: string; soft: string; deep: string; glow: string }> = {
  blue: { label: 'Hercule Blue', main: '#3b82f6', soft: 'rgba(59, 130, 246, 0.15)', deep: '#1d4ed8', glow: 'rgba(59, 130, 246, 0.35)' },
  violet: { label: 'Nebula Violet', main: '#8b5cf6', soft: 'rgba(139, 92, 246, 0.15)', deep: '#6d28d9', glow: 'rgba(139, 92, 246, 0.35)' },
  emerald: { label: 'Circuit Emerald', main: '#10b981', soft: 'rgba(16, 185, 129, 0.15)', deep: '#047857', glow: 'rgba(16, 185, 129, 0.35)' },
  amber: { label: 'Solar Amber', main: '#f59e0b', soft: 'rgba(245, 158, 11, 0.15)', deep: '#b45309', glow: 'rgba(245, 158, 11, 0.35)' },
};

const FONT_SIZES: Record<FontScale, string> = {
  compact: '13px',
  regular: '14px',
  large: '15px',
};

interface ThemeValue {
  accent: AccentName;
  setAccent: (a: AccentName) => void;
  fontScale: FontScale;
  setFontScale: (f: FontScale) => void;
}

const ThemeContext = createContext<ThemeValue | null>(null);

function readStored<T extends string>(key: string, fallback: T, allowed: readonly string[]): T {
  try {
    const raw = localStorage.getItem(key);
    if (raw && (allowed as readonly string[]).includes(raw)) return raw as T;
  } catch {
    // ignore
  }
  return fallback;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [accent, setAccentState] = useState<AccentName>(() =>
    readStored('hercule-theme-accent', 'blue', ['blue', 'violet', 'emerald', 'amber'])
  );
  const [fontScale, setFontScaleState] = useState<FontScale>(() =>
    readStored('hercule-theme-font', 'regular', ['compact', 'regular', 'large'])
  );

  useEffect(() => {
    const root = document.documentElement;
    const def = ACCENTS[accent];
    root.dataset.accent = accent;
    root.style.setProperty('--theme-accent', def.main);
    root.style.setProperty('--theme-accent-soft', def.soft);
    root.style.setProperty('--theme-accent-deep', def.deep);
    root.style.setProperty('--theme-accent-glow', def.glow);
    root.style.fontSize = FONT_SIZES[fontScale];
    try {
      localStorage.setItem('hercule-theme-accent', accent);
      localStorage.setItem('hercule-theme-font', fontScale);
    } catch {
      // ignore
    }
  }, [accent, fontScale]);

  const value = useMemo<ThemeValue>(
    () => ({
      accent,
      setAccent: setAccentState,
      fontScale,
      setFontScale: setFontScaleState,
    }),
    [accent, fontScale]
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used inside ThemeProvider');
  return ctx;
}
