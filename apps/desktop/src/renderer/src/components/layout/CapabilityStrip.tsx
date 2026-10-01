import { Bot, Brain, Plug, Wrench, CheckSquare } from 'lucide-react';
import { cn } from '@/src/utils/cn';
import { useTools, usePlugins } from '@/src/hooks/useIntegrations';
import { useMemories, useTasks } from '@/src/hooks/useWorkspace';
import { useAppConfig } from '@/src/hooks/useAppConfig';

interface CapabilityStripProps {
  modelStatus: string;
  currentModel: string | null;
}

export function CapabilityStrip({ modelStatus, currentModel }: CapabilityStripProps) {
  const { activeCount: toolsCount } = useTools();
  const { connectedCount: pluginsCount } = usePlugins();
  const { memories } = useMemories();
  const { openCount: openTasks } = useTasks();
  const { num } = useAppConfig();

  const running = modelStatus === 'running';
  const effectiveCtx = num('ctxSizeEffective', 0);
  const ctxLabel = effectiveCtx > 0 ? `${Math.round(effectiveCtx / 1024)}K context` : 'Local engine';

  const items = [
    {
      icon: <Bot className="w-3.5 h-3.5" />,
      label: currentModel ?? 'No model',
      active: running,
      hint: running ? 'Model running locally' : currentModel ? 'Model ready — start it to chat' : 'Download a model to begin',
    },
    {
      icon: <Brain className="w-3.5 h-3.5" />,
      label: ctxLabel,
      active: running,
      hint: running ? 'Active conversation context window' : 'Start the model to use its context window',
    },
    {
      icon: <Wrench className="w-3.5 h-3.5" />,
      label: `${toolsCount} tools`,
      active: toolsCount > 0,
      hint: 'Enabled built-in tools',
    },
    {
      icon: <Plug className="w-3.5 h-3.5" />,
      label: `${pluginsCount} plugins`,
      active: pluginsCount > 0,
      hint: 'Connected integrations',
    },
    {
      icon: <CheckSquare className="w-3.5 h-3.5" />,
      label: `${openTasks} open · ${memories.length} memories`,
      active: true,
      hint: 'Your workspace at a glance',
    },
  ];

  return (
    <div className="flex items-center gap-2 px-5 py-2 border-b border-border-primary bg-bg-secondary/60 overflow-x-auto">
      <span className="text-[11px] font-semibold uppercase tracking-wider text-text-tertiary flex-shrink-0 mr-1">
        Right now
      </span>
      {items.map((item, i) => (
        <span
          key={i}
          title={item.hint}
          className={cn(
            'flex flex-shrink-0 items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full border transition-colors',
            item.active
              ? 'bg-slate-800/60 text-text-secondary border-border-primary'
              : 'bg-slate-800/30 text-text-muted border-border-primary/60'
          )}
        >
          {i === 0 ? (
            <span className={cn('flex h-1.5 w-1.5 rounded-full', running ? 'bg-emerald-500 animate-pulse' : 'bg-amber-500')} />
          ) : (
            <span className="text-text-tertiary">{item.icon}</span>
          )}
          <span className="whitespace-nowrap">{item.label}</span>
        </span>
      ))}
    </div>
  );
}
