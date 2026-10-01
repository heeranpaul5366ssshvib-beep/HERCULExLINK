import { forwardRef, type HTMLAttributes } from 'react';

export interface ContainerProps extends HTMLAttributes<HTMLDivElement> {
  size?: 'sm' | 'md' | 'lg' | 'xl' | 'full';
}

export const Container = forwardRef<HTMLDivElement, ContainerProps>(
  ({ size = 'lg', children, className = '', ...props }, ref) => {
    const sizeClasses = {
      sm: 'container-sm',
      md: 'container-md',
      lg: 'container-lg',
      xl: 'container-xl',
      full: 'container-full',
    };

    const classNames = [
      'container',
      sizeClasses[size],
      className,
    ].filter(Boolean).join(' ');

    return (
      <div ref={ref} className={classNames} {...props}>
        {children}
      </div>
    );
  }
);

Container.displayName = 'Container';