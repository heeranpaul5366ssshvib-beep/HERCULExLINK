import { forwardRef, type HTMLAttributes } from 'react';

export interface ProgressProps extends HTMLAttributes<HTMLDivElement> {
  value: number;
  max?: number;
  size?: 'sm' | 'md' | 'lg';
  color?: 'primary' | 'secondary' | 'success' | 'warning' | 'error';
  showLabel?: boolean;
  label?: string;
  indeterminate?: boolean;
}

export const Progress = forwardRef<HTMLDivElement, ProgressProps>(
  (
    {
      value,
      max = 100,
      size = 'md',
      color = 'primary',
      showLabel = false,
      label,
      indeterminate = false,
      className = '',
      ...props
    },
    ref
  ) => {
    const percentage = Math.min(Math.max((value / max) * 100, 0), 100);

    const sizeClasses = {
      sm: 'progress-sm',
      md: 'progress-md',
      lg: 'progress-lg',
    };

    const colorClasses = {
      primary: 'progress-primary',
      secondary: 'progress-secondary',
      success: 'progress-success',
      warning: 'progress-warning',
      error: 'progress-error',
    };

    const classNames = [
      'progress',
      sizeClasses[size],
      colorClasses[color],
      indeterminate && 'progress-indeterminate',
      className,
    ].filter(Boolean).join(' ');

    return (
      <div ref={ref} className={classNames} role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={max} {...props}>
        <div className="progress-track">
          <div
            className="progress-fill"
            style={{ width: indeterminate ? 'auto' : `${percentage}%` }}
          />
        </div>
        {(showLabel || label) && (
          <div className="progress-label">
            {label || `${Math.round(percentage)}%`}
          </div>
        )}
      </div>
    );
  }
);

Progress.displayName = 'Progress';

export interface CircularProgressProps extends HTMLAttributes<HTMLDivElement> {
  value: number;
  max?: number;
  size?: number;
  strokeWidth?: number;
  color?: 'primary' | 'secondary' | 'success' | 'warning' | 'error';
  showValue?: boolean;
}

export const CircularProgress = forwardRef<HTMLDivElement, CircularProgressProps>(
  (
    {
      value,
      max = 100,
      size = 48,
      strokeWidth = 4,
      color = 'primary',
      showValue = true,
      className = '',
      ...props
    },
    ref
  ) => {
    const percentage = Math.min(Math.max((value / max) * 100, 0), 100);
    const radius = (size - strokeWidth) / 2;
    const circumference = 2 * Math.PI * radius;
    const offset = circumference - (percentage / 100) * circumference;

    const colorClasses = {
      primary: 'circular-progress-primary',
      secondary: 'circular-progress-secondary',
      success: 'circular-progress-success',
      warning: 'circular-progress-warning',
      error: 'circular-progress-error',
    };

    const classNames = [
      'circular-progress',
      colorClasses[color],
      className,
    ].filter(Boolean).join(' ');

    return (
      <div ref={ref} className={classNames} style={{ width: size, height: size }} role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={max} {...props}>
        <svg width={size} height={size} className="circular-progress-svg">
          <circle
            className="circular-progress-bg"
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            strokeWidth={strokeWidth}
          />
          <circle
            className="circular-progress-circle"
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            style={{ transition: 'stroke-dashoffset 0.3s ease' }}
          />
        </svg>
        {showValue && (
          <div className="circular-progress-value">
            {Math.round(percentage)}%
          </div>
        )}
      </div>
    );
  }
);

CircularProgress.displayName = 'CircularProgress';