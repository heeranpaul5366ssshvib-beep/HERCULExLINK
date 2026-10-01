import { forwardRef, type HTMLAttributes } from 'react';
import { cn } from '../../utils/cn';

export interface BreadcrumbItem {
  label: string;
  href?: string;
  onClick?: () => void;
  current?: boolean;
  disabled?: boolean;
}

export interface BreadcrumbsProps extends HTMLAttributes<HTMLElement> {
  items: BreadcrumbItem[];
  separator?: React.ReactNode;
  maxItems?: number;
  collapsible?: boolean;
}

export const Breadcrumbs = forwardRef<HTMLElement, BreadcrumbsProps>(
  ({
    items,
    separator = <span className="breadcrumbs-separator" aria-hidden="true">/</span>,
    maxItems = 5,
    collapsible = true,
    className = '',
    'aria-label': ariaLabel = 'Breadcrumb',
    ...props
  }, ref) => {
    const visibleItems = items.length > maxItems && collapsible
      ? [
          items[0],
          { label: '...', disabled: true } as BreadcrumbItem,
          ...items.slice(-(maxItems - 2)),
        ]
      : items;

    const classNames = [
      'breadcrumbs',
      className,
    ].filter(Boolean).join(' ');

    return (
      <nav ref={ref} className={classNames} aria-label={ariaLabel} {...props}>
        <ol className="breadcrumbs-list">
          {visibleItems.map((item, index) => {
            if (!item) return null;
            return (
              <li key={item.label || index} className="breadcrumbs-item">
                {index > 0 && <span className="breadcrumbs-separator-wrapper">{separator}</span>}
                {item.href ? (
                  <a href={item.href} className={cn('breadcrumbs-link', item.current && 'breadcrumbs-link-current')}>
                    {item.label}
                  </a>
                ) : item.onClick ? (
                  <button
                    type="button"
                    onClick={item.onClick}
                    className={cn('breadcrumbs-link', item.current && 'breadcrumbs-link-current')}
                    disabled={item.disabled}
                    aria-current={item.current ? 'page' : undefined}
                  >
                    {item.label}
                  </button>
                ) : (
                  <span className={cn('breadcrumbs-label', item.current && 'breadcrumbs-label-current')} aria-current={item.current ? 'page' : undefined}>
                    {item.label}
                  </span>
                )}
              </li>
            );
          })}
        </ol>
      </nav>
    );
  }
);

Breadcrumbs.displayName = 'Breadcrumbs';