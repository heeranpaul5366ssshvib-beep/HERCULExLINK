import { forwardRef, type HTMLAttributes } from 'react';

export interface SpinnerProps extends HTMLAttributes<HTMLDivElement> {
  size?: 'sm' | 'md' | 'lg';
  color?: 'primary' | 'secondary' | 'white';
}

export const Spinner = forwardRef<HTMLDivElement, SpinnerProps>(
  ({ size = 'md', color = 'primary', className = '', ...props }, ref) => {
    const sizeClasses = {
      sm: 'spinner-sm',
      md: 'spinner-md',
      lg: 'spinner-lg',
    };

    const colorClasses = {
      primary: 'spinner-primary',
      secondary: 'spinner-secondary',
      white: 'spinner-white',
    };

    const classNames = [
      'spinner',
      sizeClasses[size],
      colorClasses[color],
      className,
    ].filter(Boolean).join(' ');

    return (
      <div ref={ref} className={classNames} role="status" aria-label="Loading" {...props}>
        <svg className="spinner-svg" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <circle
            className="spinner-circle-bg"
            cx="12"
            cy="12"
            r="10"
            strokeWidth="3"
          />
          <circle
            className="spinner-circle"
            cx="12"
            cy="12"
            r="10"
            strokeWidth="3"
            strokeLinecap="round"
            strokeDasharray="31.4 31.4"
          >
            <animateTransform
              attributeName="transform"
              type="rotate"
              from="0 12 12"
              to="360 12 12"
              dur="1s"
              repeatCount="indefinite"
            />
          </circle>
        </svg>
      </div>
    );
  }
);

Spinner.displayName = 'Spinner';