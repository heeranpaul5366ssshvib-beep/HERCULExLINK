import { forwardRef, type HTMLAttributes } from 'react';

export interface GridProps extends HTMLAttributes<HTMLDivElement> {
  columns?: number | { base?: number; sm?: number; md?: number; lg?: number; xl?: number };
  gap?: 'none' | 'sm' | 'md' | 'lg' | 'xl';
  rows?: number;
}

export const Grid = forwardRef<HTMLDivElement, GridProps>(
  ({ columns = 1, gap = 'md', rows, children, className = '', style, ...props }, ref) => {
    const columnStyles = (() => {
      if (typeof columns === 'number') {
        return `grid-template-columns: repeat(${columns}, minmax(0, 1fr));`;
      }
      const { base = 1, sm, md, lg, xl } = columns;
      return `
        grid-template-columns: repeat(${base}, minmax(0, 1fr));
        @media (min-width: 640px) { grid-template-columns: repeat(${sm ?? base}, minmax(0, 1fr)); }
        @media (min-width: 768px) { grid-template-columns: repeat(${md ?? sm ?? base}, minmax(0, 1fr)); }
        @media (min-width: 1024px) { grid-template-columns: repeat(${lg ?? md ?? sm ?? base}, minmax(0, 1fr)); }
        @media (min-width: 1280px) { grid-template-columns: repeat(${xl ?? lg ?? md ?? sm ?? base}, minmax(0, 1fr)); }
      `;
    })();

    const gapStyles = {
      none: 'gap-0',
      sm: 'gap-2',
      md: 'gap-4',
      lg: 'gap-6',
      xl: 'gap-8',
    };

    const classNames = [
      'grid',
      gapStyles[gap],
      className,
    ].filter(Boolean).join(' ');

    return (
      <div
        ref={ref}
        className={classNames}
        style={{
          ...style,
          ...(columnStyles && { cssText: columnStyles }),
          ...(rows && { gridTemplateRows: `repeat(${rows}, minmax(0, 1fr))` }),
        }}
        {...props}
      >
        {children}
      </div>
    );
  }
);

Grid.displayName = 'Grid';