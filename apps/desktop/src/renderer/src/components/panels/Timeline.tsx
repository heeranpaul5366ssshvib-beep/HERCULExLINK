import { cn } from '@/src/utils/cn';
import { CheckCircle, Info, AlertTriangle, Loader2, Clock } from 'lucide-react';

export interface TimelineEvent {
  time: string;
  type: 'success' | 'info' | 'warning' | 'loading';
  message: string;
  details: string;
}

interface TimelineProps {
  events: TimelineEvent[];
}

const TYPE_CONFIG = {
  success: { icon: CheckCircle, color: 'text-emerald-400', bg: 'bg-emerald-500/15', border: 'border-emerald-500/20' },
  info: { icon: Info, color: 'text-blue-400', bg: 'bg-blue-500/15', border: 'border-blue-500/20' },
  warning: { icon: AlertTriangle, color: 'text-amber-400', bg: 'bg-amber-500/15', border: 'border-amber-500/20' },
  loading: { icon: Loader2, color: 'text-violet-400', bg: 'bg-violet-500/15', border: 'border-violet-500/20' },
};

export function Timeline({ events }: TimelineProps) {
  return (
    <div className="relative pl-6">
      <div className="absolute left-[5px] top-0 bottom-0 w-0.5 bg-gradient-to-b from-border-secondary to-transparent" />
      {events.map((event, index) => {
        const config = TYPE_CONFIG[event.type];
        const Icon = config.icon;
        return (
          <div key={index} className="relative pb-6 last:pb-0 animate-slide-up" style={{ animationDelay: `${index * 50}ms` }}>
            <div className="absolute left-[-6px] top-1 flex h-3 w-3 items-center justify-center">
              <div className={cn('w-2 h-2 rounded-full border-2 border-bg-secondary', config.color.replace('text-', 'bg-'))} />
            </div>
            <div className={cn('pl-3 p-3 rounded-lg border transition-all', config.bg, config.border)}>
              <div className="flex items-start gap-3">
                <div className={cn('flex-shrink-0 flex h-7 w-7 items-center justify-center rounded-lg', config.bg)}>
                  <Icon className={cn('w-3.5 h-3.5', config.color)} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <p className="font-medium text-text-primary truncate">{event.message}</p>
                    <span className="flex-shrink-0 text-xs text-text-muted font-mono">{event.time}</span>
                  </div>
                  <p className="mt-1 text-sm text-text-tertiary">{event.details}</p>
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}