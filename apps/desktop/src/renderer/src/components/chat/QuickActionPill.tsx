import { cn } from '@/src/utils/cn';

interface QuickActionPillProps {
  label: string;
  icon: React.ReactNode;
  onClick: () => void;
}

export function QuickActionPill({ label, icon, onClick }: QuickActionPillProps) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-full transition-all duration-200',
        'bg-slate-800/50 text-text-secondary border border-border-primary',
        'hover:bg-slate-800 hover:text-text-primary hover:border-border-secondary',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500'
      )}
      aria-label={label}
    >
      <span className="flex-shrink-0">{icon}</span>
      <span>{label}</span>
    </button>
  );
}