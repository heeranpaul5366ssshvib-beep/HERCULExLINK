import { useState, useEffect, forwardRef, type HTMLAttributes } from 'react';

export interface ToastProps extends HTMLAttributes<HTMLDivElement> {
  variant?: 'info' | 'success' | 'warning' | 'error';
  title?: string;
  duration?: number;
  onClose?: () => void;
  action?: React.ReactNode;
}

export const Toast = forwardRef<HTMLDivElement, ToastProps>(
  (
    {
      variant = 'info',
      title,
      duration = 5000,
      onClose,
      action,
      children,
      className = '',
      ...props
    },
    ref
  ) => {
    const [isVisible, setIsVisible] = useState(true);

    useEffect(() => {
      if (duration > 0) {
        const timer = setTimeout(() => {
          setIsVisible(false);
          onClose?.();
        }, duration);
        return () => clearTimeout(timer);
      }
    }, [duration, onClose]);

    if (!isVisible) return null;

    const variantClasses = {
      info: 'toast-info',
      success: 'toast-success',
      warning: 'toast-warning',
      error: 'toast-error',
    };

    const classNames = [
      'toast',
      variantClasses[variant],
      className,
    ].filter(Boolean).join(' ');

    return (
      <div ref={ref} className={classNames} role="alert" {...props}>
        <div className="toast-content">
          {title && <div className="toast-title">{title}</div>}
          <div className="toast-message">{children}</div>
        </div>
        {action && <div className="toast-action">{action}</div>}
        <button
          type="button"
          className="toast-dismiss"
          onClick={() => { setIsVisible(false); onClose?.(); }}
          aria-label="Dismiss toast"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
    );
  }
);

Toast.displayName = 'Toast';

export interface ToastContainerProps {
  position?: 'top-right' | 'top-left' | 'bottom-right' | 'bottom-left' | 'top-center' | 'bottom-center';
  children: React.ReactNode;
}

export function ToastContainer({ position = 'top-right', children }: ToastContainerProps) {
  const positionClasses = {
    'top-right': 'toast-container-top-right',
    'top-left': 'toast-container-top-left',
    'bottom-right': 'toast-container-bottom-right',
    'bottom-left': 'toast-container-bottom-left',
    'top-center': 'toast-container-top-center',
    'bottom-center': 'toast-container-bottom-center',
  };

  return (
    <div className={`toast-container ${positionClasses[position]}`} role="region" aria-label="Notifications">
      {children}
    </div>
  );
}