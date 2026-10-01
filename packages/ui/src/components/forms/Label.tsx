import { forwardRef, type LabelHTMLAttributes } from 'react';

export interface LabelProps extends LabelHTMLAttributes<HTMLLabelElement> {
  required?: boolean;
  size?: 'sm' | 'md' | 'lg';
}

export const Label = forwardRef<HTMLLabelElement, LabelProps>(
  ({ required = false, size = 'md', children, className = '', ...props }, ref) => {
    const sizeClasses = {
      sm: 'label-sm',
      md: 'label-md',
      lg: 'label-lg',
    };

    const classNames = [
      'label',
      sizeClasses[size],
      className,
    ].filter(Boolean).join(' ');

    return (
      <label ref={ref} className={classNames} {...props}>
        {children}
        {required && <span className="label-required" aria-hidden="true">*</span>}
      </label>
    );
  }
);

Label.displayName = 'Label';