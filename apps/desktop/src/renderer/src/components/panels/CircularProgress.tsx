import { useId } from 'react';

interface CircularProgressProps {
  value: number;
  size?: number;
  strokeWidth?: number;
  color?: 'blue' | 'violet' | 'emerald' | 'amber';
  showValue?: boolean;
}

const COLOR_STOPS = {
  blue: ['#3b82f6', '#8b5cf6'],
  violet: ['#8b5cf6', '#a78bfa'],
  emerald: ['#10b981', '#34d399'],
  amber: ['#f59e0b', '#fbbf24'],
} as const;

const GLOW_COLORS = {
  blue: 'rgba(59, 130, 246, 0.45)',
  violet: 'rgba(139, 92, 246, 0.45)',
  emerald: 'rgba(16, 185, 129, 0.45)',
  amber: 'rgba(245, 158, 11, 0.45)',
} as const;

export function CircularProgress({ value, size = 64, strokeWidth = 6, color = 'blue', showValue = true }: CircularProgressProps) {
  const uid = useId().replace(/[^a-zA-Z0-9]/g, '');
  const gradientId = `cp-gradient-${uid}`;
  const clamped = Math.min(100, Math.max(0, value));
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (clamped / 100) * circumference;
  const [from, to] = COLOR_STOPS[color];

  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="block">
        <defs>
          <linearGradient id={gradientId} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor={from} />
            <stop offset="100%" stopColor={to} />
          </linearGradient>
          <filter id={`${gradientId}-glow`} x="-60%" y="-60%" width="220%" height="220%">
            <feDropShadow dx="0" dy="0" stdDeviation="2.5" floodColor={GLOW_COLORS[color]} floodOpacity="0.9" />
          </filter>
        </defs>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="#1e293b"
          strokeWidth={strokeWidth}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={`url(#${gradientId})`}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          filter={`url(#${gradientId}-glow)`}
          style={{ transition: 'stroke-dashoffset 0.5s ease-out' }}
        />
      </svg>
      {showValue && (
        <div
          className="absolute inset-0 flex items-center justify-center font-mono font-bold"
          style={{ color: '#f1f5f9', fontSize: Math.max(11, size * 0.2) }}
        >
          {Math.round(clamped)}%
        </div>
      )}
    </div>
  );
}
