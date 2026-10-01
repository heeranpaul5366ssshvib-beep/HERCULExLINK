import { forwardRef, type InputHTMLAttributes, useId } from 'react';

export interface RadioProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  description?: string;
}

export const Radio = forwardRef<HTMLInputElement, RadioProps>(
  (
    {
      label,
      description,
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
      'radio-wrapper',
      className,
    ].filter(Boolean).join(' ');

    return (
      <div className={classNames}>
        <label htmlFor={id} className="radio-label">
          <div className="radio-input-wrapper">
            <input
              ref={ref}
              type="radio"
              id={id}
              className="radio-input"
              disabled={disabled}
              required={required}
              {...props}
            />
            <div className="radio-icon" aria-hidden="true">
              <span className="radio-dot" />
            </div>
          </div>
          {(label || description) && (
            <div className="radio-content">
              {label && <span className="radio-label-text">{label}</span>}
              {description && <span className="radio-description">{description}</span>}
            </div>
          )}
        </label>
      </div>
    );
  }
);

Radio.displayName = 'Radio';

export interface RadioGroupProps {
  name: string;
  options: Array<{ value: string; label: string; description?: string; disabled?: boolean }>;
  value?: string;
  onChange?: (value: string) => void;
  required?: boolean;
  disabled?: boolean;
  className?: string;
}

export function RadioGroup({ name, options, value, onChange, required, disabled, className = '' }: RadioGroupProps) {
  return (
    <div className={`radio-group ${className}`} role="radiogroup" aria-required={required}>
      {options.map((option) => (
        <Radio
          key={option.value}
          name={name}
          value={option.value}
          checked={value === option.value}
          onChange={(e) => onChange?.(e.target.value)}
          label={option.label}
          description={option.description}
          disabled={disabled || option.disabled}
          required={required}
        />
      ))}
    </div>
  );
}