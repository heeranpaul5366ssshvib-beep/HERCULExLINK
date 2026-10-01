import { forwardRef, type HTMLAttributes } from 'react';

export interface StackProps extends HTMLAttributes<HTMLDivElement> {
  direction?: 'vertical' | 'horizontal';
  gap?: 'none' | 'sm' | 'md' | 'lg' | 'xl';
  align?: 'start' | 'center' | 'end' | 'stretch';
  justify?: 'start' | 'center' | 'end' | 'between' | 'around';
  divider?: React.ReactNode;
}

export const Stack = forwardRef<HTMLDivElement, StackProps>(
  ({
    direction = 'vertical',
    gap = 'md',
    align = 'stretch',
    justify = 'start',
    divider,
    children,
    className = '',
    style,
    ...props
  }, ref) => {
    const gapStyles = {
      none: 'gap-0',
      sm: 'gap-2',
      md: 'gap-4',
      lg: 'gap-6',
      xl: 'gap-8',
    };

    const alignStyles = {
      start: direction === 'vertical' ? 'items-start' : 'justify-content-start',
      center: direction === 'vertical' ? 'items-center' : 'justify-content-center',
      end: direction === 'vertical' ? 'items-end' : 'justify-content-end',
      stretch: direction === 'vertical' ? 'items-stretch' : 'items-stretch',
    };

    const justifyStyles = {
      start: direction === 'vertical' ? 'justify-content-start' : 'items-start',
      center: direction === 'vertical' ? 'justify-content-center' : 'items-center',
      end: direction === 'vertical' ? 'justify-content-end' : 'items-end',
      between: 'justify-content-between',
      around: 'justify-content-around',
    };

    const childrenArray = Array.isArray(children) ? children : [children];
    const childrenWithDividers = divider && childrenArray.length > 1
      ? childrenArray.flatMap((child, index) => [
          child,
          index < childrenArray.length - 1 ? <div key={`divider-${index}`} className="stack-divider">{divider}</div> : null,
        ])
      : childrenArray;

    const classNames = [
      'stack',
      direction === 'vertical' ? 'flex-col' : 'flex-row',
      gapStyles[gap],
      alignStyles[align],
      justifyStyles[justify],
      className,
    ].filter(Boolean).join(' ');

    return (
      <div ref={ref} className={classNames} style={style} {...props}>
        {childrenWithDividers}
      </div>
    );
  }
);

Stack.displayName = 'Stack';

export interface HStackProps extends StackProps {
  direction?: 'horizontal';
}

export const HStack = forwardRef<HTMLDivElement, HStackProps>(
  ({ direction, ...props }, ref) => (
    <Stack ref={ref} direction="horizontal" {...props} />
  )
);

HStack.displayName = 'HStack';

export interface VStackProps extends StackProps {
  direction?: 'vertical';
}

export const VStack = forwardRef<HTMLDivElement, VStackProps>(
  ({ direction, ...props }, ref) => (
    <Stack ref={ref} direction="vertical" {...props} />
  )
);

VStack.displayName = 'VStack';