import { forwardRef, type InputHTMLAttributes, type TextareaHTMLAttributes, useId } from 'react';
import './Input.css';

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  hint?: string;
  leftElement?: React.ReactNode;
  rightElement?: React.ReactNode;
  fullWidth?: boolean;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  (
    {
      label,
      error,
      hint,
      leftElement,
      rightElement,
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
    ]
      .filter(Boolean)
      .join(' ');

    return (
      <div className={wrapperClassNames}>
        {label && (
          <label htmlFor={id} className="input-label">
            {label}
            {required && <span className="input-required" aria-hidden="true">*</span>}
          </label>
        )}
        <div className="input-group">
          {leftElement && <span className="input-element input-element-left">{leftElement}</span>}
          <input
            ref={ref}
            id={id}
            className={`input ${error ? 'input-error' : ''}`}
            disabled={disabled}
            required={required}
            aria-invalid={error ? 'true' : 'false'}
            aria-describedby={describedBy}
            aria-required={required}
            {...props}
          />
          {rightElement && <span className="input-element input-element-right">{rightElement}</span>}
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

Input.displayName = 'Input';

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
  hint?: string;
  fullWidth?: boolean;
  resize?: 'none' | 'vertical' | 'horizontal' | 'both';
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  (
    {
      label,
      error,
      hint,
      fullWidth = true,
      resize = 'vertical',
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
    ]
      .filter(Boolean)
      .join(' ');

    return (
      <div className={wrapperClassNames}>
        {label && (
          <label htmlFor={id} className="input-label">
            {label}
            {required && <span className="input-required" aria-hidden="true">*</span>}
          </label>
        )}
        <textarea
          ref={ref}
          id={id}
          className={`input textarea ${error ? 'input-error' : ''}`}
          disabled={disabled}
          required={required}
          aria-invalid={error ? 'true' : 'false'}
          aria-describedby={describedBy}
          aria-required={required}
          style={{ resize }}
          {...props}
        />
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

Textarea.displayName = 'Textarea';