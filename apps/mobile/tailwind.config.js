/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./src/**/*.{js,ts,jsx,tsx,html}",
    "./src/index.html",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        bg: {
          primary: '#0d1326',
          secondary: '#0f172a',
          tertiary: '#111827',
          card: '#141c2f',
          'card-hover': '#1a243d',
          elevated: '#1e293b',
        },
        border: {
          primary: '#1e293b',
          secondary: '#334155',
          focus: '#3b82f6',
        },
        text: {
          primary: '#f1f5f9',
          secondary: '#94a3b8',
          tertiary: '#64748b',
          muted: '#475569',
        },
        accent: {
          blue: '#3b82f6',
          'blue-glow': '#60a5fa',
          violet: '#8b5cf6',
          'violet-glow': '#a78bfa',
          emerald: '#10b981',
          'emerald-glow': '#34d399',
          amber: '#f59e0b',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      boxShadow: {
        'glow-blue': '0 0 20px rgb(59 130 246 / 0.3)',
        'glow-violet': '0 0 20px rgb(139 92 246 / 0.3)',
        'glow-emerald': '0 0 20px rgb(16 185 129 / 0.3)',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'slide-up': 'slideUp 0.3s ease-out forwards',
        'fade-in': 'fadeIn 0.2s ease-out forwards',
      },
      keyframes: {
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
      },
    },
  },
  plugins: [],
}
