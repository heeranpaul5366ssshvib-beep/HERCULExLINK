import { cn } from '@/src/utils/cn';
import { CheckCircle, XCircle, ExternalLink, Loader2 } from 'lucide-react';

interface PluginCardProps {
  plugin: {
    id: string;
    name: string;
    icon: React.ReactNode;
    status: 'connected' | 'disconnected' | 'connecting' | 'error';
    color: 'blue' | 'violet' | 'emerald' | 'amber';
  };
}

const STATUS_CONFIG = {
  connected: { icon: CheckCircle, color: 'text-emerald-400', bg: 'bg-emerald-500/15', label: 'Connected' },
  disconnected: { icon: XCircle, color: 'text-slate-500', bg: 'bg-slate-500/15', label: 'Disconnected' },
  connecting: { icon: Loader2, color: 'text-blue-400', bg: 'bg-blue-500/15', label: 'Connecting...' },
  error: { icon: XCircle, color: 'text-red-400', bg: 'bg-red-500/15', label: 'Error' },
};

const COLOR_CONFIG = {
  blue: 'bg-blue-500/10 border-blue-500/20 hover:bg-blue-500/20',
  violet: 'bg-violet-500/10 border-violet-500/20 hover:bg-violet-500/20',
  emerald: 'bg-emerald-500/10 border-emerald-500/20 hover:bg-emerald-500/20',
  amber: 'bg-amber-500/10 border-amber-500/20 hover:bg-amber-500/20',
};

export function PluginCard({ plugin }: PluginCardProps) {
  const statusConfig = STATUS_CONFIG[plugin.status];

  return (
    <button className={cn(
      'relative flex flex-col p-4 rounded-xl transition-all duration-200',
      'bg-slate-900/30 border border-border-primary',
      'hover:border-border-secondary hover:bg-slate-900/50',
      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500',
      COLOR_CONFIG[plugin.color]
    )}>
      <div className="flex items-start justify-between mb-3">
        <div className={cn('flex h-10 w-10 items-center justify-center rounded-lg', COLOR_CONFIG[plugin.color].replace('hover:', ''))}>
          {plugin.icon}
        </div>
        <div className={cn('flex h-5 w-5 items-center justify-center rounded', statusConfig.bg)}>
          <statusConfig.icon className={cn('w-3 h-3', statusConfig.color)} />
        </div>
      </div>
      <h4 className="font-medium text-text-primary mb-1">{plugin.name}</h4>
      <p className={cn('text-xs font-medium', statusConfig.color)}>{statusConfig.label}</p>
      {plugin.status === 'connected' && (
        <button
          className="mt-3 flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs font-medium text-text-tertiary hover:text-text-primary hover:bg-slate-800/50 rounded-lg transition-colors"
        >
          <ExternalLink className="w-3.5 h-3.5" />
          <span>Open</span>
        </button>
      )}
    </button>
  );
}