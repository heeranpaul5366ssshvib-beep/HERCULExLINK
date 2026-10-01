/**
 * HERCULE Design Tokens
 * Cross-platform design system tokens for consistent styling
 */

export const colors = {
  // Brand colors
  brand: {
    50: '#f0f5ff',
    100: '#e0ebff',
    200: '#c7d9fe',
    300: '#a5bdfd',
    400: '#8197fb',
    500: '#6366f1', // Primary
    600: '#4f46e5',
    700: '#4338ca',
    800: '#3730a3',
    900: '#312e81',
    950: '#1e1b4b',
  },

  // Semantic colors
  semantic: {
    success: {
      light: '#dcfce7',
      main: '#22c55e',
      dark: '#166534',
    },
    warning: {
      light: '#fef3c7',
      main: '#f59e0b',
      dark: '#92400e',
    },
    error: {
      light: '#fee2e2',
      main: '#ef4444',
      dark: '#991b1b',
    },
    info: {
      light: '#dbeafe',
      main: '#3b82f6',
      dark: '#1e40af',
    },
  },

  // Neutral colors
  neutral: {
    0: '#ffffff',
    50: '#fafafa',
    100: '#f5f5f5',
    200: '#e5e5e5',
    300: '#d4d4d4',
    400: '#a3a3a3',
    500: '#737373',
    600: '#525252',
    700: '#404040',
    800: '#262626',
    900: '#171717',
    950: '#0a0a0a',
  },

  // Surface colors (auto light/dark)
  surface: {
    primary: 'var(--surface-primary, #ffffff)',
    secondary: 'var(--surface-secondary, #fafafa)',
    tertiary: 'var(--surface-tertiary, #f5f5f5)',
    elevated: 'var(--surface-elevated, #ffffff)',
    overlay: 'var(--surface-overlay, rgba(0, 0, 0, 0.5))',
  },

  // Text colors
  text: {
    primary: 'var(--text-primary, #171717)',
    secondary: 'var(--text-secondary, #525252)',
    tertiary: 'var(--text-tertiary, #737373)',
    inverse: 'var(--text-inverse, #ffffff)',
    disabled: 'var(--text-disabled, #a3a3a3)',
    link: 'var(--text-link, #6366f1)',
  },

  // Border colors
  border: {
    light: 'var(--border-light, #e5e5e5)',
    main: 'var(--border-main, #d4d4d4)',
    dark: 'var(--border-dark, #a3a3a3)',
    focus: 'var(--border-focus, #6366f1)',
  },
} as const;

export const spacing = {
  0: '0',
  1: '0.25rem',  // 4px
  2: '0.5rem',   // 8px
  3: '0.75rem',  // 12px
  4: '1rem',     // 16px
  5: '1.25rem',  // 20px
  6: '1.5rem',   // 24px
  8: '2rem',     // 32px
  10: '2.5rem',  // 40px
  12: '3rem',    // 48px
  16: '4rem',    // 64px
  20: '5rem',    // 80px
  24: '6rem',    // 96px
} as const;

export const typography = {
  fontFamilies: {
    sans: 'var(--font-sans, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif)',
    mono: 'var(--font-mono, ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace)',
    display: 'var(--font-display, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif)',
  },
  fontSizes: {
    xs: '0.75rem',    // 12px
    sm: '0.875rem',   // 14px
    base: '1rem',     // 16px
    lg: '1.125rem',   // 18px
    xl: '1.25rem',    // 20px
    '2xl': '1.5rem',  // 24px
    '3xl': '1.875rem', // 30px
    '4xl': '2.25rem', // 36px
    '5xl': '3rem',    // 48px
    '6xl': '3.75rem', // 60px
  },
  fontWeights: {
    normal: 400,
    medium: 500,
    semibold: 600,
    bold: 700,
  },
  lineHeights: {
    tight: 1.25,
    normal: 1.5,
    relaxed: 1.75,
  },
  letterSpacings: {
    tight: '-0.02em',
    normal: '0',
    wide: '0.02em',
  },
} as const;

export const borderRadius = {
  none: '0',
  sm: '0.25rem',   // 4px
  md: '0.375rem',  // 6px
  lg: '0.5rem',    // 8px
  xl: '0.75rem',   // 12px
  '2xl': '1rem',   // 16px
  full: '9999px',
} as const;

export const shadows = {
  none: 'none',
  sm: '0 1px 2px 0 rgb(0 0 0 / 0.05)',
  md: '0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)',
  lg: '0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)',
  xl: '0 20px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1)',
  '2xl': '0 25px 50px -12px rgb(0 0 0 / 0.25)',
  inner: 'inset 0 2px 4px 0 rgb(0 0 0 / 0.05)',
  focus: '0 0 0 3px var(--border-focus, #6366f1)',
} as const;

export const transitions = {
  fast: '150ms ease',
  normal: '200ms ease',
  slow: '300ms ease',
} as const;

export const zIndex = {
  hide: -1,
  base: 0,
  dropdown: 1000,
  sticky: 1100,
  modal: 1300,
  popover: 1400,
  toast: 1500,
  tooltip: 1600,
} as const;

export const breakpoints = {
  sm: '640px',
  md: '768px',
  lg: '1024px',
  xl: '1280px',
  '2xl': '1536px',
} as const;

export type ColorScale = typeof colors.brand;
export type SpacingScale = typeof spacing;
export type TypographyScale = typeof typography;