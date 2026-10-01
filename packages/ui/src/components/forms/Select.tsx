import { forwardRef, type SelectHTMLAttributes, useId } from 'react';

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  error?: string;
  hint?: string;
  options: SelectOption[];
  placeholder?: string;
  fullWidth?: boolean;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  (
    {
      label,
      error,
      hint,
      options,
      placeholder,
      fullWidth = true,
      id: providedId,
      className = '',
      disabled,
      required,
      'aria-describedby': ariaDescribedBy,
      ...props
    },
    ref
  ) => {
    const generatedId = useId();
    const id = providedId || generatedId;
    const errorId = error ? `${id}-error` : undefined;
    const hintId = hint ? `${id}-hint` : undefined;
    const describedBy = [errorId, hintId, ariaDescribedBy].filter(Boolean).join(' ') || undefined;

    const wrapperClassNames = [
      'input-wrapper',
      fullWidth && 'input-wrapper-full',
      error && 'input-wrapper-error',
      disabled && 'input-wrapper-disabled',
      className,
    ].filter(Boolean).join(' ');

    return (
      <div className={wrapperClassNames}>
        {label && (
          <label htmlFor={id} className="input-label">
            {label}
            {required && <span className="input-required" aria-hidden="true">*</span>}
          </label>
        )}
        <div className="select-wrapper">
          <select
            ref={ref}
            id={id}
            className={`select ${error ? 'select-error' : ''}`}
            disabled={disabled}
            required={required}
            aria-invalid={error ? 'true' : 'false'}
            aria-describedby={describedBy}
            aria-required={required}
            {...props}
          >
            {placeholder && (
              <option value="" disabled>
                {placeholder}
              </option>
            )}
            {options.map((option) => (
              <option key={option.value} value={option.value} disabled={option.disabled}>
                {option.label}
              </option>
            ))}
          </select>
          <svg className="select-arrow" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </div>
        {error && (
          <p id={errorId} className="input-error-message" role="alert">
            {error}
          </p>
        )}
        {hint && !error && (
          <p id={hintId} className="input-hint">
            {hint}
          </p>
        )}
      </div>
    );
  }
);

Select.displayName = 'Select';