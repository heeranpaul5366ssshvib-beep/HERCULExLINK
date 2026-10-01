import { forwardRef, type InputHTMLAttributes, useId } from 'react';

export interface SwitchProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'size'> {
  label?: string;
  description?: string;
  size?: 'sm' | 'md' | 'lg';
}

export const Switch = forwardRef<HTMLInputElement, SwitchProps>(
  (
    {
      label,
      description,
      size = 'md',
      id: providedId,
      className = '',
      disabled,
      required,
      ...props
    },
    ref
  ) => {
    const generatedId = useId();
    const id = providedId || generatedId;

    const sizeClasses = {
      sm: 'switch-sm',
      md: 'switch-md',
      lg: 'switch-lg',
    };

    const classNames = [
      'switch-wrapper',
      sizeClasses[size],
      className,
    ].filter(Boolean).join(' ');

    return (
      <div className={classNames}>
        <label htmlFor={id} className="switch-label">
          <div className="switch-input-wrapper">
            <input
              ref={ref}
              type="checkbox"
              id={id}
              className="switch-input"
              disabled={disabled}
              required={required}
              {...props}
            />
            <div className="switch-track" aria-hidden="true">
              <div className="switch-thumb" />
            </div>
          </div>
          {(label || description) && (
            <div className="switch-content">
              {label && <span className="switch-label-text">{label}</span>}
              {description && <span className="switch-description">{description}</span>}
            </div>
          )}
        </label>
      </div>
    );
  }
);

Switch.displayName = 'Switch';