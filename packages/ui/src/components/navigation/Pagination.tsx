import { forwardRef, type HTMLAttributes } from 'react';
import { cn } from '../../utils/cn';

export interface PaginationProps extends HTMLAttributes<HTMLElement> {
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  showFirstLast?: boolean;
  showPrevNext?: boolean;
  siblingCount?: number;
  boundaryCount?: number;
  size?: 'sm' | 'md' | 'lg';
  variant?: 'default' | 'outline';
}

export const Pagination = forwardRef<HTMLElement, PaginationProps>(
  ({
    currentPage,
    totalPages,
    onPageChange,
    showFirstLast = true,
    showPrevNext = true,
    siblingCount = 1,
    boundaryCount = 1,
    size = 'md',
    variant = 'default',
    className = '',
    'aria-label': ariaLabel = 'Pagination',
    ...props
  }, ref) => {
    if (totalPages <= 1) return null;

    const sizeStyles = {
      sm: 'pagination-sm',
      md: 'pagination-md',
      lg: 'pagination-lg',
    };

    const variantStyles = {
      default: 'pagination-default',
      outline: 'pagination-outline',
    };

    const pages = getPaginationRange(currentPage, totalPages, siblingCount, boundaryCount);

    const classNames = [
      'pagination',
      sizeStyles[size],
      variantStyles[variant],
      className,
    ].filter(Boolean).join(' ');

    return (
      <nav ref={ref} className={classNames} aria-label={ariaLabel} {...props}>
        <ul className="pagination-list">
          {showFirstLast && (
            <>
              <li>
                <button
                  type="button"
                  className="pagination-item pagination-first"
                  onClick={() => onPageChange(1)}
                  disabled={currentPage === 1}
                  aria-label="First page"
                  aria-disabled={currentPage === 1}
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
                  </svg>
                </button>
              </li>
              <li>
                <button
                  type="button"
                  className="pagination-item pagination-prev"
                  onClick={() => onPageChange(currentPage - 1)}
                  disabled={currentPage === 1}
                  aria-label="Previous page"
                  aria-disabled={currentPage === 1}
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                  </svg>
                </button>
              </li>
            </>
          )}

          {pages.map((page, index) => (
            <li key={page} className="pagination-page-wrapper">
              {page === 'ellipsis' ? (
                <span className="pagination-ellipsis" aria-hidden="true">…</span>
              ) : (
                <button
                  type="button"
                  className={cn(
                    'pagination-item pagination-page',
                    page === currentPage && 'pagination-page-active'
                  )}
                  onClick={() => onPageChange(page as number)}
                  disabled={page === currentPage}
                  aria-label={`Page ${page}`}
                  aria-current={page === currentPage ? 'page' : undefined}
                >
                  {page}
                </button>
              )}
            </li>
          ))}

          {showFirstLast && (
            <>
              <li>
                <button
                  type="button"
                  className="pagination-item pagination-next"
                  onClick={() => onPageChange(currentPage + 1)}
                  disabled={currentPage === totalPages}
                  aria-label="Next page"
                  aria-disabled={currentPage === totalPages}
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                </button>
              </li>
              <li>
                <button
                  type="button"
                  className="pagination-item pagination-last"
                  onClick={() => onPageChange(totalPages)}
                  disabled={currentPage === totalPages}
                  aria-label="Last page"
                  aria-disabled={currentPage === totalPages}
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 5l7 7-7 7M5 5l7 7-7 7" />
                  </svg>
                </button>
              </li>
            </>
          )}
        </ul>
      </nav>
    );
  }
);

Pagination.displayName = 'Pagination';

function getPaginationRange(
  currentPage: number,
  totalPages: number,
  siblingCount: number,
  boundaryCount: number
): Array<number | 'ellipsis'> {
  const totalPageNumbers = siblingCount * 2 + 3 + boundaryCount * 2;

  if (totalPageNumbers >= totalPages) {
    return Array.from({ length: totalPages }, (_, i) => i + 1);
  }

  const leftBoundary = Array.from({ length: boundaryCount }, (_, i) => i + 1);
  const rightBoundary = Array.from({ length: boundaryCount }, (_, i) => totalPages - boundaryCount + 1 + i);

  const leftSiblingStart = Math.max(boundaryCount + 1, currentPage - siblingCount);
  const leftSiblingEnd = Math.min(currentPage - 1, totalPages - boundaryCount);

  const rightSiblingStart = Math.max(currentPage + 1, boundaryCount + 1);
  const rightSiblingEnd = Math.min(totalPages - boundaryCount, currentPage + siblingCount);

  const leftSiblings = leftSiblingStart <= leftSiblingEnd
    ? Array.from({ length: leftSiblingEnd - leftSiblingStart + 1 }, (_, i) => leftSiblingStart + i)
    : [];

  const rightSiblings = rightSiblingStart <= rightSiblingEnd
    ? Array.from({ length: rightSiblingEnd - rightSiblingStart + 1 }, (_, i) => rightSiblingStart + i)
    : [];

  const result: Array<number | 'ellipsis'> = [];

  result.push(...leftBoundary);

  const lastLeftBoundary: number = leftBoundary[leftBoundary.length - 1] ?? 0;
  const firstLeftSibling: number | undefined = leftSiblings[0];
  if (firstLeftSibling !== undefined && firstLeftSibling > lastLeftBoundary + 1) {
    result.push('ellipsis');
  }

  result.push(...leftSiblings);

  if (!leftSiblings.includes(currentPage) && !rightSiblings.includes(currentPage) && currentPage !== 1 && currentPage !== totalPages) {
    result.push(currentPage);
  }

  result.push(...rightSiblings);

  const firstRightBoundary: number = rightBoundary[0] ?? 0;
  const lastRightSibling: number | undefined = rightSiblings[rightSiblings.length - 1];
  if (lastRightSibling !== undefined && lastRightSibling < firstRightBoundary - 1) {
    result.push('ellipsis');
  }

  result.push(...rightBoundary);

  return result;
}