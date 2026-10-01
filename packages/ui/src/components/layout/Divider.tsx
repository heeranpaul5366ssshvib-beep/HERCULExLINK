import { forwardRef, type HTMLAttributes } from 'react';

export interface DividerProps extends HTMLAttributes<HTMLDivElement> {
  orientation?: 'horizontal' | 'vertical';
  variant?: 'solid' | 'dashed' | 'dotted';
  thickness?: 'thin' | 'medium' | 'thick';
  color?: 'default' | 'muted' | 'primary';
  label?: string;
  labelPosition?: 'start' | 'center' | 'end';
}

export const Divider = forwardRef<HTMLDivElement, DividerProps>(
  ({
    orientation = 'horizontal',
    variant = 'solid',
    thickness = 'thin',
    color = 'default',
    label,
    labelPosition = 'center',
    className = '',
    style,
    ...props
  }, ref) => {
    const orientationStyles = {
      horizontal: 'divider-horizontal',
      vertical: 'divider-vertical',
    };

    const variantStyles = {
      solid: 'divider-solid',
      dashed: 'divider-dashed',
      dotted: 'divider-dotted',
    };

    const thicknessStyles = {
      thin: 'divider-thin',
      medium: 'divider-medium',
      thick: 'divider-thick',
    };

    const colorStyles = {
      default: 'divider-default',
      muted: 'divider-muted',
      primary: 'divider-primary',
    };

    const classNames = [
      'divider',
      orientationStyles[orientation],
      variantStyles[variant],
      thicknessStyles[thickness],
      colorStyles[color],
      label && 'divider-with-label',
      className,
    ].filter(Boolean).join(' ');

    if (label) {
      return (
        <div ref={ref} className={classNames} style={style} role="separator" {...props}>
          {labelPosition !== 'end' && <div className="divider-before" />}
          <span className="divider-label">{label}</span>
          {labelPosition !== 'start' && <div className="divider-after" />}
        </div>
      );
    }

    return (
      <div ref={ref} className={classNames} style={style} role="separator" {...props} />
    );
  }
);

Divider.displayName = 'Divider';