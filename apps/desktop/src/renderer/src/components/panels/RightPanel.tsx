import { useState } from 'react';
import { cn } from '@/src/utils/cn';
import { Github, Globe, HardDrive, Monitor, Activity, CheckCircle, Loader2, XCircle, AlertTriangle, ExternalLink, Brain, Cpu, MemoryStick, Server } from 'lucide-react';
import { CircularProgress } from '@/src/components/panels/CircularProgress';
import { Timeline, type TimelineEvent } from '@/src/components/panels/Timeline';
import { PluginCard } from '@/src/components/panels/PluginCard';

interface RightPanelProps {
  stats: { cpu: number; ram: number; storage: number; gpu: number };
  isLoading: boolean;
  modelStatus: string;
  currentModel?: string | null;
  ctxSize?: number;
}

const SYSTEM_METRICS = [
  { key: 'cpu', label: 'CPU', icon: <Cpu className="w-4 h-4" />, color: 'blue' },
  { key: 'ram', label: 'RAM', icon: <MemoryStick className="w-4 h-4" />, color: 'violet' },
  { key: 'storage', label: 'Storage', icon: <HardDrive className="w-4 h-4" />, color: 'emerald' },
  { key: 'gpu', label: 'GPU', icon: <Server className="w-4 h-4" />, color: 'amber' },
] as const;

const TIMELINE_EVENTS: TimelineEvent[] = [
  { time: '10:42 AM', type: 'success', message: 'Model inference completed', details: 'Tokens: 247 · Latency: 1.2s' },
  { time: '10:38 AM', type: 'info', message: 'Chat session started', details: 'Context: 4.2k tokens' },
  { time: '10:35 AM', type: 'success', message: 'Task completed', details: 'Code review for auth module' },
  { time: '10:30 AM', type: 'warning', message: 'Plugin update available', details: 'GitHub integration v2.1.0' },
  { time: '10:25 AM', type: 'info', message: 'Memory sync', details: '12 entries synchronized' },
];

const PLUGINS = [
  { id: 'github', name: 'GitHub', icon: <Github className="w-5 h-5" />, status: 'connected', color: 'violet', description: 'Repositories & Issues' },
  { id: 'web', name: 'Web Search', icon: <Globe className="w-5 h-5" />, status: 'connected', color: 'blue', description: 'Real-time search' },
  { id: 'drive', name: 'Google Drive', icon: <HardDrive className="w-5 h-5" />, status: 'disconnected', color: 'emerald', description: 'File access' },
  { id: 'vscode', name: 'VS Code', icon: <Monitor className="w-5 h-5" />, status: 'connected', color: 'blue', description: 'Editor integration' },
] as const;

export function RightPanel({ stats, isLoading, modelStatus, currentModel, ctxSize }: RightPanelProps) {
  const ctxLabel = ctxSize && ctxSize > 0 ? `${ctxSize.toLocaleString()} tokens` : '—';
  const ctxShort = ctxSize && ctxSize > 0 ? `${Math.round(ctxSize / 1024)}K / ${Math.round(ctxSize / 1024)}K` : '—';
  const [activeTab, setActiveTab] = useState<'system' | 'activity' | 'plugins'>('system');

  return (
    <aside className="w-80 flex flex-col bg-bg-secondary border-l border-border-primary overflow-hidden">
      <div className="flex h-12 items-center justify-between px-4 border-b border-border-primary">
        <h2 className="text-sm font-semibold text-text-primary">Monitoring</h2>
        <div className="flex items-center gap-1">
          {['system', 'activity', 'plugins'].map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab as any)}
              className={cn(
                'px-2.5 py-1 text-xs font-medium rounded-md transition-colors',
                activeTab === tab
                  ? 't-nav-active'
                  : 'text-text-tertiary hover:text-text-primary hover:bg-bg-tertiary'
              )}
            >
              {tab.charAt(0).toUpperCase() + tab.slice(1)}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {activeTab === 'system' && (
          <>
            <div className="card p-4">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-medium text-text-primary">System Status</h3>
                <span className={cn(
                  'flex items-center gap-1.5 px-2 py-0.5 text-xs font-medium rounded-full',
                  modelStatus === 'running' ? 'bg-emerald-500/15 text-emerald-400' : 'bg-amber-500/15 text-amber-400'
                )}>
                  <span className={cn('w-1.5 h-1.5 rounded-full', modelStatus === 'running' ? 'bg-emerald-500 animate-pulse' : 'bg-amber-500 animate-pulse')} />
                  {modelStatus === 'running' ? 'Live' : 'Idle'}
                </span>
              </div>
              <div className="grid grid-cols-4 gap-2">
                {SYSTEM_METRICS.map(({ key, label, icon, color }) => (
                  <div key={key} className="flex min-w-0 flex-col items-center">
                    <div className="mb-1.5">
                      <CircularProgress
                        value={isLoading ? 0 : stats[key as keyof typeof stats]}
                        size={60}
                        strokeWidth={6}
                        color={color}
                      />
                    </div>
                    <div className="flex items-center gap-1 text-[11px] text-text-secondary mb-0.5">
                      {icon}
                      <span className="font-medium text-text-primary">{label}</span>
                    </div>
                    <span className={cn('text-xs font-mono font-semibold', isLoading ? 'text-text-muted' : 'text-text-primary')}>
                      {isLoading ? '—' : `${stats[key as keyof typeof stats]}%`}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <div className="card p-4">
              <h3 className="font-medium text-text-primary mb-3">Model Status</h3>
              <div className="space-y-3">
                <div className="flex items-center justify-between p-3 rounded-lg bg-slate-800/50 border border-border-primary">
                  <div className="flex items-center gap-3">
                    <div className={cn('flex h-8 w-8 items-center justify-center rounded-lg', modelStatus === 'running' ? 'bg-emerald-500/20' : 'bg-slate-700')}>
                      {modelStatus === 'running' ? (
                        <Activity className="w-4 h-4 text-emerald-400" />
                      ) : (
                        <Loader2 className="w-4 h-4 text-text-tertiary" />
                      )}
                    </div>
                    <div>
                      <p className="font-medium text-text-primary">Inference Engine</p>
                      <p className="text-xs text-text-tertiary">llama.cpp · GGUF</p>
                    </div>
                  </div>
                  <span className={cn(
                    'px-2 py-1 text-xs font-medium rounded-full',
                    modelStatus === 'running' ? 'bg-emerald-500/15 text-emerald-400' : 'bg-slate-700 text-text-tertiary'
                  )}>
                    {modelStatus}
                  </span>
                </div>
                <div className="flex items-center justify-between p-3 rounded-lg bg-slate-800/50 border border-border-primary">
                  <div className="flex items-center gap-3">
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-500/20">
                      <Brain className="w-4 h-4 text-blue-400" />
                    </div>
                    <div>
                      <p className="font-medium text-text-primary">Context Window</p>
                      <p className="text-xs text-text-tertiary">{ctxLabel}</p>
                    </div>
                  </div>
                  <span className="text-sm font-mono text-text-secondary">{ctxShort}</span>
                </div>
                <div className="flex items-center justify-between p-3 rounded-lg bg-slate-800/50 border border-border-primary">
                  <div className="flex items-center gap-3">
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-violet-500/20">
                      <Brain className="w-4 h-4 text-violet-400" />
                    </div>
                    <div className="min-w-0">
                      <p className="font-medium text-text-primary">Model</p>
                      <p className="text-xs text-text-tertiary truncate" title={currentModel ?? 'No model selected'}>
                        {currentModel ?? 'No model selected'}
                      </p>
                    </div>
                  </div>
                  <span className="text-sm font-mono text-text-secondary">v1.0.0</span>
                </div>
              </div>
            </div>
          </>
        )}

        {activeTab === 'activity' && (
          <div className="card p-4">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-medium text-text-primary">Current Activity</h3>
              <span className="flex items-center gap-1.5 px-2 py-0.5 text-xs font-medium rounded-full bg-emerald-500/15 text-emerald-400">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                Live
              </span>
            </div>
            <Timeline events={TIMELINE_EVENTS} />
          </div>
        )}

        {activeTab === 'plugins' && (
          <div className="card p-4">
            <h3 className="font-medium text-text-primary mb-4">Plugins</h3>
            <div className="grid grid-cols-2 gap-3">
              {PLUGINS.map((plugin) => (
                <PluginCard key={plugin.id} plugin={plugin} />
              ))}
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}