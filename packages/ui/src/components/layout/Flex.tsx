import { forwardRef, type HTMLAttributes } from 'react';

export interface FlexProps extends HTMLAttributes<HTMLDivElement> {
  direction?: 'row' | 'col' | 'row-reverse' | 'col-reverse';
  wrap?: 'wrap' | 'nowrap' | 'wrap-reverse';
  justify?: 'start' | 'center' | 'end' | 'between' | 'around' | 'evenly';
  align?: 'start' | 'center' | 'end' | 'stretch' | 'baseline';
  gap?: 'none' | 'sm' | 'md' | 'lg' | 'xl';
  fullWidth?: boolean;
  fullHeight?: boolean;
}

export const Flex = forwardRef<HTMLDivElement, FlexProps>(
  ({
    direction = 'row',
    wrap = 'nowrap',
    justify = 'start',
    align = 'stretch',
    gap = 'none',
    fullWidth = false,
    fullHeight = false,
    children,
    className = '',
    style,
    ...props
  }, ref) => {
    const directionStyles = {
      row: 'flex-row',
      col: 'flex-col',
      'row-reverse': 'flex-row-reverse',
      'col-reverse': 'flex-col-reverse',
    };

    const wrapStyles = {
      wrap: 'flex-wrap',
      nowrap: 'flex-nowrap',
      'wrap-reverse': 'flex-wrap-reverse',
    };

    const justifyStyles = {
      start: 'justify-content-start',
      center: 'justify-content-center',
      end: 'justify-content-end',
      between: 'justify-content-between',
      around: 'justify-content-around',
      evenly: 'justify-content-evenly',
    };

    const alignStyles = {
      start: 'items-start',
      center: 'items-center',
      end: 'items-end',
      stretch: 'items-stretch',
      baseline: 'items-baseline',
    };

    const gapStyles = {
      none: 'gap-0',
      sm: 'gap-2',
      md: 'gap-4',
      lg: 'gap-6',
      xl: 'gap-8',
    };

    const classNames = [
      'flex',
      directionStyles[direction],
      wrapStyles[wrap],
      justifyStyles[justify],
      alignStyles[align],
      gapStyles[gap],
      fullWidth && 'w-full',
      fullHeight && 'h-full',
      className,
    ].filter(Boolean).join(' ');

    return (
      <div ref={ref} className={classNames} style={style} {...props}>
        {children}
      </div>
    );
  }
);

Flex.displayName = 'Flex';