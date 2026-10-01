import { Wrench, Code, Globe, Search, Calculator, CalendarCheck, Brain } from 'lucide-react';
import { cn } from '@/src/utils/cn';
import { useTools } from '@/src/hooks/useIntegrations';

const TOOL_ICONS: Record<string, React.ReactNode> = {
  'code-runner': <Code className="w-5 h-5" />,
  'web-fetch': <Globe className="w-5 h-5" />,
  'file-search': <Search className="w-5 h-5" />,
  calculator: <Calculator className="w-5 h-5" />,
  'task-planner': <CalendarCheck className="w-5 h-5" />,
  memory: <Brain className="w-5 h-5" />,
};

function Toggle({ on, onChange, label }: { on: boolean; onChange: () => void; label: string }) {
  return (
    <button
      role="switch"
      aria-checked={on}
      aria-label={label}
      onClick={onChange}
      className={cn(
        'relative flex-shrink-0 h-6 w-11 rounded-full transition-colors duration-200',
        on ? 't-toggle-on' : 'bg-slate-700'
      )}
    >
      <span
        className={cn(
          'absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all duration-200',
          on ? 'left-[22px]' : 'left-0.5'
        )}
      />
    </button>
  );
}

export function ToolsView() {
  const { tools, enabled, toggle, activeCount } = useTools();

  return (
    <div className="mx-auto w-full max-w-3xl px-6 py-8">
      <div className="flex items-center gap-3 mb-1">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-500/10 text-amber-400 border border-amber-500/20">
          <Wrench className="w-5 h-5" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-text-primary tracking-tight">Tools</h1>
          <p className="text-sm text-text-tertiary">{activeCount} of {tools.length} built-in tools enabled</p>
        </div>
      </div>

      <p className="mt-4 text-sm text-text-tertiary">
        Tools are capabilities HERCULE can use while answering — running code, fetching pages, searching your files. Toggle them to control what it may do.
      </p>

      <div className="mt-4 space-y-2">
        {tools.map((tool) => {
          const on = enabled[tool.id] !== false;
          return (
            <div key={tool.id} className="card p-4 flex items-start gap-3">
              <div className={cn(
                'flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl border',
                on ? 't-accent-bg-soft t-accent-text t-accent-border' : 'bg-slate-800/50 text-text-muted border-border-primary'
              )}>
                {TOOL_ICONS[tool.id] ?? <Wrench className="w-5 h-5" />}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="font-semibold text-text-primary">{tool.name}</h3>
                  <Toggle on={on} onChange={() => toggle(tool.id)} label={`Toggle ${tool.name}`} />
                </div>
                <p className="mt-1 text-sm text-text-tertiary">{tool.description}</p>
                <p className="mt-1.5 text-xs font-mono text-text-muted">Try: {tool.usage}</p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
