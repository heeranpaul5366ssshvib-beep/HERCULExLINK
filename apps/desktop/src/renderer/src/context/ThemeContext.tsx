import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

export type AccentName = 'blue' | 'violet' | 'emerald' | 'amber' | 'rose' | 'cyan' | 'orange' | 'custom';
export type ThemeMode = 'dark' | 'midnight' | 'light';
export type FontScale = 'compact' | 'regular' | 'large';
export type FontFamily = 'inter' | 'system' | 'serif' | 'mono';
export type RadiusChoice = 'sharp' | 'smooth' | 'round' | 'pill';
export type DensityChoice = 'compact' | 'comfortable' | 'spacious';
export type ChatStyle = 'bubbles' | 'minimal' | 'cards';
export type SidebarSide = 'left' | 'right';
export type ChatWidth = 'narrow' | 'wide' | 'full';
export type BgEffect = 'none' | 'gradient' | 'grid' | 'glow' | 'aurora';

export interface AccentDef {
  label: string;
  main: string;
  soft: string;
  deep: string;
  glow: string;
}

export const ACCENTS: Record<Exclude<AccentName, 'custom'>, AccentDef> = {
  blue: { label: 'Hercule Blue', main: '#3b82f6', soft: 'rgba(59, 130, 246, 0.15)', deep: '#1d4ed8', glow: 'rgba(59, 130, 246, 0.35)' },
  violet: { label: 'Nebula Violet', main: '#8b5cf6', soft: 'rgba(139, 92, 246, 0.15)', deep: '#6d28d9', glow: 'rgba(139, 92, 246, 0.35)' },
  emerald: { label: 'Circuit Emerald', main: '#10b981', soft: 'rgba(16, 185, 129, 0.15)', deep: '#047857', glow: 'rgba(16, 185, 129, 0.35)' },
  amber: { label: 'Solar Amber', main: '#f59e0b', soft: 'rgba(245, 158, 11, 0.15)', deep: '#b45309', glow: 'rgba(245, 158, 11, 0.35)' },
  rose: { label: 'Pulse Rose', main: '#f43f5e', soft: 'rgba(244, 63, 94, 0.15)', deep: '#be123c', glow: 'rgba(244, 63, 94, 0.35)' },
  cyan: { label: 'Ion Cyan', main: '#06b6d4', soft: 'rgba(6, 182, 212, 0.15)', deep: '#0e7490', glow: 'rgba(6, 182, 212, 0.35)' },
  orange: { label: 'Forge Orange', main: '#f97316', soft: 'rgba(249, 115, 22, 0.15)', deep: '#c2410c', glow: 'rgba(249, 115, 22, 0.35)' },
};

const FONT_SIZES: Record<FontScale, string> = {
  compact: '13px',
  regular: '14px',
  large: '15.5px',
};

const FONT_STACKS: Record<FontFamily, string> = {
  inter: "'Inter', system-ui, -apple-system, sans-serif",
  system: "system-ui, -apple-system, 'Segoe UI', sans-serif",
  serif: "'Georgia', 'Times New Roman', serif",
  mono: "'JetBrains Mono', 'Cascadia Code', monospace",
};

const RADIUS_PX: Record<RadiusChoice, string> = {
  sharp: '6px',
  smooth: '10px',
  round: '14px',
  pill: '20px',
};

function hexToRgb(hex: string): [number, number, number] | null {
  const m = hex.trim().replace('#', '');
  const full = m.length === 3 ? m.split('').map((c) => c + c).join('') : m;
  if (!/^[0-9a-fA-F]{6}$/.test(full)) return null;
  const n = parseInt(full, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function shade(hex: string, factor: number): string {
  const rgb = hexToRgb(hex);
  if (!rgb) return hex;
  const r = Math.max(0, Math.min(255, Math.round(rgb[0] * factor)));
  const g = Math.max(0, Math.min(255, Math.round(rgb[1] * factor)));
  const b = Math.max(0, Math.min(255, Math.round(rgb[2] * factor)));
  return `#${((r << 16) | (g << 8) | b).toString(16).padStart(6, '0')}`;
}

function accentDefFor(accent: AccentName, customHex: string): AccentDef {
  if (accent !== 'custom') return ACCENTS[accent];
  const rgb = hexToRgb(customHex);
  if (!rgb) return ACCENTS.blue;
  const [r, g, b] = rgb;
  return {
    label: 'Custom',
    main: customHex,
    soft: `rgba(${r}, ${g}, ${b}, 0.15)`,
    deep: shade(customHex, 0.7),
    glow: `rgba(${r}, ${g}, ${b}, 0.35)`,
  };
}

function readStored<T extends string>(key: string, fallback: T, allowed: readonly string[]): T {
  try {
    const raw = localStorage.getItem(key);
    if (raw && (allowed as readonly string[]).includes(raw)) return raw as T;
  } catch {
    // ignore
  }
  return fallback;
}

function readBool(key: string, fallback: boolean): boolean {
  try {
    const raw = localStorage.getItem(key);
    if (raw === '1' || raw === 'true') return true;
    if (raw === '0' || raw === 'false') return false;
  } catch {
    // ignore
  }
  return fallback;
}

function readHex(key: string, fallback: string): string {
  try {
    const raw = localStorage.getItem(key);
    if (raw && /^#[0-9a-fA-F]{6}$/.test(raw)) return raw;
  } catch {
    // ignore
  }
  return fallback;
}

function writeStore(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // ignore
  }
}

export interface ThemeValue {
  // legacy (kept for existing components)
  accent: AccentName;
  setAccent: (a: AccentName) => void;
  fontScale: FontScale;
  setFontScale: (f: FontScale) => void;
  // studio
  themeMode: ThemeMode;
  setThemeMode: (m: ThemeMode) => void;
  fontFamily: FontFamily;
  setFontFamily: (f: FontFamily) => void;
  radius: RadiusChoice;
  setRadius: (r: RadiusChoice) => void;
  density: DensityChoice;
  setDensity: (d: DensityChoice) => void;
  chatStyle: ChatStyle;
  setChatStyle: (c: ChatStyle) => void;
  sidebarSide: SidebarSide;
  setSidebarSide: (s: SidebarSide) => void;
  chatWidth: ChatWidth;
  setChatWidth: (w: ChatWidth) => void;
  bgEffect: BgEffect;
  setBgEffect: (b: BgEffect) => void;
  customAccent: string;
  setCustomAccent: (hex: string) => void;
  showAvatars: boolean;
  setShowAvatars: (v: boolean) => void;
  showRightPanel: boolean;
  setShowRightPanel: (v: boolean) => void;
  animations: boolean;
  setAnimations: (v: boolean) => void;
  resetAppearance: () => void;
}

const ThemeContext = createContext<ThemeValue | null>(null);

const ACCENT_KEYS: readonly string[] = ['blue', 'violet', 'emerald', 'amber', 'rose', 'cyan', 'orange', 'custom'];

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [accent, setAccentState] = useState<AccentName>(() => readStored('hercule-theme-accent', 'blue', ACCENT_KEYS));
  const [fontScale, setFontScaleState] = useState<FontScale>(() =>
    readStored('hercule-theme-font', 'regular', ['compact', 'regular', 'large'])
  );
  const [themeMode, setThemeModeState] = useState<ThemeMode>(() =>
    readStored('hercule-ui-theme', 'dark', ['dark', 'midnight', 'light'])
  );
  const [fontFamily, setFontFamilyState] = useState<FontFamily>(() =>
    readStored('hercule-ui-font-family', 'inter', ['inter', 'system', 'serif', 'mono'])
  );
  const [radius, setRadiusState] = useState<RadiusChoice>(() =>
    readStored('hercule-ui-radius', 'round', ['sharp', 'smooth', 'round', 'pill'])
  );
  const [density, setDensityState] = useState<DensityChoice>(() =>
    readStored('hercule-ui-density', 'comfortable', ['compact', 'comfortable', 'spacious'])
  );
  const [chatStyle, setChatStyleState] = useState<ChatStyle>(() =>
    readStored('hercule-ui-chat', 'bubbles', ['bubbles', 'minimal', 'cards'])
  );
  const [sidebarSide, setSidebarSideState] = useState<SidebarSide>(() =>
    readStored('hercule-ui-sidebar', 'left', ['left', 'right'])
  );
  const [chatWidth, setChatWidthState] = useState<ChatWidth>(() =>
    readStored('hercule-ui-width', 'narrow', ['narrow', 'wide', 'full'])
  );
  const [bgEffect, setBgEffectState] = useState<BgEffect>(() =>
    readStored('hercule-ui-bg', 'gradient', ['none', 'gradient', 'grid', 'glow', 'aurora'])
  );
  const [customAccent, setCustomAccentState] = useState<string>(() => readHex('hercule-ui-custom-accent', '#ec4899'));
  const [showAvatars, setShowAvatarsState] = useState<boolean>(() => readBool('hercule-ui-avatars', true));
  const [showRightPanel, setShowRightPanelState] = useState<boolean>(() => readBool('hercule-ui-rightpanel', true));
  const [animations, setAnimationsState] = useState<boolean>(() => readBool('hercule-ui-motion', true));

  useEffect(() => {
    const root = document.documentElement;
    const def = accentDefFor(accent, customAccent);
    root.dataset.accent = accent;
    root.dataset.theme = themeMode;
    root.dataset.radius = radius;
    root.dataset.density = density;
    root.dataset.chat = chatStyle;
    root.dataset.sidebar = sidebarSide;
    root.dataset.bg = bgEffect;
    root.dataset.motion = animations ? 'on' : 'off';
    root.style.setProperty('--theme-accent', def.main);
    root.style.setProperty('--theme-accent-soft', def.soft);
    root.style.setProperty('--theme-accent-deep', def.deep);
    root.style.setProperty('--theme-accent-glow', def.glow);
    root.style.setProperty('--ui-radius', RADIUS_PX[radius]);
    root.style.fontSize = FONT_SIZES[fontScale];
    root.style.colorScheme = themeMode === 'light' ? 'light' : 'dark';
    document.body.style.fontFamily = FONT_STACKS[fontFamily];

    writeStore('hercule-theme-accent', accent);
    writeStore('hercule-theme-font', fontScale);
    writeStore('hercule-ui-theme', themeMode);
    writeStore('hercule-ui-font-family', fontFamily);
    writeStore('hercule-ui-radius', radius);
    writeStore('hercule-ui-density', density);
    writeStore('hercule-ui-chat', chatStyle);
    writeStore('hercule-ui-sidebar', sidebarSide);
    writeStore('hercule-ui-width', chatWidth);
    writeStore('hercule-ui-bg', bgEffect);
    writeStore('hercule-ui-custom-accent', customAccent);
    writeStore('hercule-ui-avatars', showAvatars ? '1' : '0');
    writeStore('hercule-ui-rightpanel', showRightPanel ? '1' : '0');
    writeStore('hercule-ui-motion', animations ? '1' : '0');
  }, [accent, customAccent, fontScale, themeMode, fontFamily, radius, density, chatStyle, sidebarSide, chatWidth, bgEffect, showAvatars, showRightPanel, animations]);

  const resetAppearance = useCallback(() => {
    setAccentState('blue');
    setFontScaleState('regular');
    setThemeModeState('dark');
    setFontFamilyState('inter');
    setRadiusState('round');
    setDensityState('comfortable');
    setChatStyleState('bubbles');
    setSidebarSideState('left');
    setChatWidthState('narrow');
    setBgEffectState('gradient');
    setCustomAccentState('#ec4899');
    setShowAvatarsState(true);
    setShowRightPanelState(true);
    setAnimationsState(true);
  }, []);

  const value = useMemo<ThemeValue>(
    () => ({
      accent,
      setAccent: setAccentState,
      fontScale,
      setFontScale: setFontScaleState,
      themeMode,
      setThemeMode: setThemeModeState,
      fontFamily,
      setFontFamily: setFontFamilyState,
      radius,
      setRadius: setRadiusState,
      density,
      setDensity: setDensityState,
      chatStyle,
      setChatStyle: setChatStyleState,
      sidebarSide,
      setSidebarSide: setSidebarSideState,
      chatWidth,
      setChatWidth: setChatWidthState,
      bgEffect,
      setBgEffect: setBgEffectState,
      customAccent,
      setCustomAccent: setCustomAccentState,
      showAvatars,
      setShowAvatars: setShowAvatarsState,
      showRightPanel,
      setShowRightPanel: setShowRightPanelState,
      animations,
      setAnimations: setAnimationsState,
      resetAppearance,
    }),
    [accent, fontScale, themeMode, fontFamily, radius, density, chatStyle, sidebarSide, chatWidth, bgEffect, customAccent, showAvatars, showRightPanel, animations, resetAppearance]
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used inside ThemeProvider');
  return ctx;
}

export const CHAT_WIDTH_CLASS: Record<ChatWidth, string> = {
  narrow: 'max-w-3xl',
  wide: 'max-w-5xl',
  full: 'max-w-none',
};
