import { forwardRef, type HTMLAttributes } from 'react';
import { cn } from '../../utils/cn';

export interface TabItem {
  value: string;
  label: string;
  disabled?: boolean;
  icon?: React.ReactNode;
  children?: React.ReactNode;
}

export interface TabsProps extends Omit<HTMLAttributes<HTMLDivElement>, 'onChange'> {
  tabs: TabItem[];
  value: string;
  onChange: (value: string) => void;
  variant?: 'line' | 'enclosed' | 'soft' | 'pills';
  orientation?: 'horizontal' | 'vertical';
  fullWidth?: boolean;
}

export const Tabs = forwardRef<HTMLDivElement, TabsProps>(
  ({
    tabs,
    value,
    onChange,
    variant = 'line',
    orientation = 'horizontal',
    fullWidth = false,
    className = '',
    style,
    ...props
  }, ref) => {
    const variantStyles = {
      line: 'tabs-line',
      enclosed: 'tabs-enclosed',
      soft: 'tabs-soft',
      pills: 'tabs-pills',
    };

    const classNames = [
      'tabs',
      variantStyles[variant],
      orientation === 'vertical' && 'tabs-vertical',
      fullWidth && 'tabs-full-width',
      className,
    ].filter(Boolean).join(' ');

    return (
      <div ref={ref} className={classNames} style={style} {...props}>
        <div className="tabs-list" role="tablist" aria-orientation={orientation}>
          {tabs.map((tab) => (
            <button
              key={tab.value}
              role="tab"
              id={`tab-${tab.value}`}
              aria-selected={value === tab.value}
              aria-controls={`panel-${tab.value}`}
              tabIndex={value === tab.value ? 0 : -1}
              onClick={() => !tab.disabled && onChange(tab.value)}
              disabled={tab.disabled}
              className={cn(
                'tabs-trigger',
                value === tab.value && 'tabs-trigger-active',
                tab.disabled && 'tabs-trigger-disabled'
              )}
            >
              {tab.icon && <span className="tabs-trigger-icon">{tab.icon}</span>}
              <span className="tabs-trigger-label">{tab.label}</span>
            </button>
          ))}
        </div>
        <div className="tabs-panels">
          {tabs.map((tab) => (
            <div
              key={tab.value}
              role="tabpanel"
              id={`panel-${tab.value}`}
              aria-labelledby={`tab-${tab.value}`}
              hidden={value !== tab.value}
              className="tabs-panel"
            >
              {tab.children}
            </div>
          ))}
        </div>
      </div>
    );
  }
);

Tabs.displayName = 'Tabs';