import { Plug, Github, Globe, HardDrive, Monitor, Terminal, FolderSearch, CalendarDays, Mail, CheckCircle2, Plus } from 'lucide-react';
import { cn } from '@/src/utils/cn';
import { usePlugins } from '@/src/hooks/useIntegrations';

const PLUGIN_ICONS: Record<string, React.ReactNode> = {
  github: <Github className="w-5 h-5" />,
  web: <Globe className="w-5 h-5" />,
  drive: <HardDrive className="w-5 h-5" />,
  vscode: <Monitor className="w-5 h-5" />,
  terminal: <Terminal className="w-5 h-5" />,
  files: <FolderSearch className="w-5 h-5" />,
  calendar: <CalendarDays className="w-5 h-5" />,
  email: <Mail className="w-5 h-5" />,
};

export function PluginsView() {
  const { plugins, enabled, toggle, connectedCount } = usePlugins();

  return (
    <div className="mx-auto w-full max-w-3xl px-6 py-8">
      <div className="flex items-center gap-3 mb-1">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-500/10 text-blue-400 border border-blue-500/20">
          <Plug className="w-5 h-5" />
        </div>
        <div className="flex-1">
          <h1 className="text-2xl font-bold text-text-primary tracking-tight">Plugins</h1>
          <p className="text-sm text-text-tertiary">{connectedCount} of {plugins.length} connected</p>
        </div>
        <button className="btn-secondary px-4 py-2 text-sm rounded-lg flex items-center gap-1.5" title="Plugin marketplace (coming soon)">
          <Plus className="w-4 h-4" /> Browse
        </button>
      </div>

      <p className="mt-4 text-sm text-text-tertiary">
        Connect HERCULE to the apps you already use. Connections run locally — credentials never leave this PC.
      </p>

      <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
        {plugins.map((plugin) => {
          const on = !!enabled[plugin.id];
          return (
            <div key={plugin.id} className={cn('card card-hover p-4 flex flex-col', on && 't-accent-border')}>
              <div className="flex items-start justify-between mb-3">
                <div className={cn(
                  'flex h-10 w-10 items-center justify-center rounded-xl border',
                  on ? 't-accent-bg-soft t-accent-text t-accent-border' : 'bg-slate-800/50 text-text-muted border-border-primary'
                )}>
                  {PLUGIN_ICONS[plugin.id] ?? <Plug className="w-5 h-5" />}
                </div>
                <span className={cn(
                  'flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full border',
                  on ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20' : 'bg-slate-800/60 text-text-muted border-border-primary'
                )}>
                  {on && <CheckCircle2 className="w-3 h-3" />}
                  {on ? 'Connected' : 'Off'}
                </span>
              </div>
              <h3 className="font-semibold text-text-primary">{plugin.name}</h3>
              <p className="text-xs text-text-muted mb-1">{plugin.category}</p>
              <p className="text-sm text-text-tertiary flex-1">{plugin.description}</p>
              <button
                onClick={() => toggle(plugin.id)}
                className={cn(
                  'mt-3 w-full px-3 py-1.5 text-sm font-medium rounded-lg border transition-all',
                  on
                    ? 'text-text-tertiary border-border-primary hover:text-red-400 hover:border-red-500/30'
                    : 't-accent-bg-soft t-accent-text t-accent-border hover:brightness-110'
                )}
              >
                {on ? 'Disconnect' : 'Connect'}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
