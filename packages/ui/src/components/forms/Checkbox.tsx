import { forwardRef, type InputHTMLAttributes, useId } from 'react';

export interface CheckboxProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  description?: string;
  indeterminate?: boolean;
}

export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(
  (
    {
      label,
      description,
      indeterminate = false,
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

    const classNames = [
      'checkbox-wrapper',
      className,
    ].filter(Boolean).join(' ');

    const inputRef = ref as React.RefObject<HTMLInputElement>;

    return (
      <div className={classNames}>
        <label htmlFor={id} className="checkbox-label">
          <div className="checkbox-input-wrapper">
            <input
              ref={inputRef}
              type="checkbox"
              id={id}
              className={`checkbox-input ${indeterminate ? 'checkbox-indeterminate' : ''}`}
              disabled={disabled}
              required={required}
              aria-checked={indeterminate ? 'mixed' : undefined}
              {...props}
            />
            <div className="checkbox-icon" aria-hidden="true">
              <svg className="checkbox-check" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
              </svg>
              <svg className="checkbox-indeterminate-icon" fill="currentColor" viewBox="0 0 24 24">
                <rect x="5" y="11" width="14" height="2" rx="1" />
              </svg>
            </div>
          </div>
          {(label || description) && (
            <div className="checkbox-content">
              {label && <span className="checkbox-label-text">{label}</span>}
              {description && <span className="checkbox-description">{description}</span>}
            </div>
          )}
        </label>
      </div>
    );
  }
);

Checkbox.displayName = 'Checkbox';