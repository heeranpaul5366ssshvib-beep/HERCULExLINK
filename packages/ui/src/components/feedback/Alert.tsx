import { forwardRef, type HTMLAttributes } from 'react';

export interface AlertProps extends HTMLAttributes<HTMLDivElement> {
  variant?: 'info' | 'success' | 'warning' | 'error';
  title?: string;
  dismissible?: boolean;
  onDismiss?: () => void;
}

export const Alert = forwardRef<HTMLDivElement, AlertProps>(
  (
    {
      variant = 'info',
      title,
      dismissible = false,
      onDismiss,
      children,
      className = '',
      ...props
    },
    ref
  ) => {
    const variantClasses = {
      info: 'alert-info',
      success: 'alert-success',
      warning: 'alert-warning',
      error: 'alert-error',
    };

    const classNames = [
      'alert',
      variantClasses[variant],
      className,
    ].filter(Boolean).join(' ');

    return (
      <div ref={ref} className={classNames} role="alert" {...props}>
        <div className="alert-content">
          {title && <div className="alert-title">{title}</div>}
          <div className="alert-message">{children}</div>
        </div>
        {dismissible && (
          <button
            type="button"
            className="alert-dismiss"
            onClick={onDismiss}
            aria-label="Dismiss alert"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        )}
      </div>
    );
  }
);

Alert.displayName = 'Alert';