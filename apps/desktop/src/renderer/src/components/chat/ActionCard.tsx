import { cn } from '@/src/utils/cn';

interface ActionCardProps {
  title: string;
  description: string;
  icon: React.ReactNode;
  accent: 'blue' | 'emerald' | 'violet' | 'amber';
  badge?: number;
  onClick: () => void;
}

const ACCENT_COLORS = {
  blue: 'bg-blue-500/10 border-blue-500/20 text-blue-400 hover:bg-blue-500/20 hover:border-blue-500/30',
  emerald: 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400 hover:bg-emerald-500/20 hover:border-emerald-500/30',
  violet: 'bg-violet-500/10 border-violet-500/20 text-violet-400 hover:bg-violet-500/20 hover:border-violet-500/30',
  amber: 'bg-amber-500/10 border-amber-500/20 text-amber-400 hover:bg-amber-500/20 hover:border-amber-500/30',
};

export function ActionCard({ title, description, icon, accent, badge, onClick }: ActionCardProps) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'relative flex flex-col p-5 rounded-xl transition-all duration-200',
        'bg-slate-900/30 border border-border-primary',
        'hover:border-border-secondary hover:bg-slate-900/50 hover:shadow-lg',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500'
      )}
    >
      <div className={cn(
        'flex h-10 w-10 items-center justify-center rounded-lg mb-3',
        ACCENT_COLORS[accent]
      )}>
        {icon}
      </div>
      <h3 className="font-semibold text-text-primary mb-1">{title}</h3>
      <p className="text-sm text-text-tertiary flex-1">{description}</p>
      {badge && (
        <span className="absolute top-3 right-3 flex h-5 min-w-[18px] items-center justify-center px-1.5 text-xs font-medium bg-slate-700 text-slate-300 rounded-full">
          {badge}
        </span>
      )}
    </button>
  );
}