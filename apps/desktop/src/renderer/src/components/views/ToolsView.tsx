import { useState } from 'react';
import { Wrench, Code, Globe, Search, Calculator, CalendarCheck, Brain, Play, FolderOpen } from 'lucide-react';
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

const RUNNABLE: Record<string, { placeholder: string; secondPlaceholder?: string; secondLabel?: string }> = {
  calculator: { placeholder: '4800 * 0.15 + sqrt(144)' },
  'file-search': { placeholder: 'search text…', secondPlaceholder: 'folder (optional)', secondLabel: 'Browse…' },
  'web-fetch': { placeholder: 'https://example.com' },
};

function ToolRunner({ toolId }: { toolId: string }) {
  const cfg = RUNNABLE[toolId];
  const [input, setInput] = useState('');
  const [second, setSecond] = useState('');
  const [output, setOutput] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [running, setRunning] = useState(false);
  if (!cfg) return null;
  const hasBridge = typeof window !== 'undefined' && !!window.electronAPI?.tools;

  const run = async () => {
    if (!hasBridge || running) return;
    setRunning(true);
    setOutput(null);
    setFailed(false);
    try {
      const toolArgs: Record<string, unknown> =
        toolId === 'calculator' ? { expression: input }
        : toolId === 'file-search' ? { query: input, ...(second.trim() ? { root: second.trim() } : {}) }
        : { url: input };
      const res = await window.electronAPI.tools.run(toolId, toolArgs);
      setOutput(res.ok ? res.output : res.error ?? 'Failed');
      setFailed(!res.ok);
    } catch (err) {
      setOutput(err instanceof Error ? err.message : 'Failed');
      setFailed(true);
    } finally {
      setRunning(false);
    }
  };

  const browse = async () => {
    try {
      const paths = await window.electronAPI.dialog.openDirectory({});
      if (paths?.[0]) setSecond(paths[0]);
    } catch {
      // dialog unavailable
    }
  };

  return (
    <div className="mt-3 rounded-lg border border-border-primary bg-slate-900/40 p-3">
      <div className="flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') run(); }}
          placeholder={cfg.placeholder}
          className="input t-focus font-mono text-xs"
          aria-label={`Try ${toolId}`}
          disabled={!hasBridge}
        />
        <button
          onClick={run}
          disabled={!hasBridge || running || !input.trim()}
          className="btn-primary px-3 py-1.5 text-xs rounded-lg flex items-center gap-1 flex-shrink-0 disabled:opacity-40"
        >
          <Play className="w-3.5 h-3.5" /> {running ? '…' : 'Run'}
        </button>
      </div>
      {toolId === 'file-search' && (
        <div className="mt-2 flex gap-2">
          <input
            value={second}
            onChange={(e) => setSecond(e.target.value)}
            placeholder={cfg.secondPlaceholder}
            className="input t-focus font-mono text-xs"
            aria-label="Search folder"
            disabled={!hasBridge}
          />
          <button onClick={browse} disabled={!hasBridge} className="btn-secondary px-3 py-1.5 text-xs rounded-lg flex items-center gap-1 flex-shrink-0" title="Pick a folder">
            <FolderOpen className="w-3.5 h-3.5" /> {cfg.secondLabel}
          </button>
        </div>
      )}
      {!hasBridge && <p className="mt-2 text-[11px] text-text-muted">Runs inside the desktop app.</p>}
      {output !== null && (
        <pre className={cn(
          'mt-2 max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-lg border p-2 font-mono text-xs',
          failed ? 'border-red-500/30 bg-red-500/5 text-red-300' : 'border-border-primary bg-slate-950/60 text-text-secondary'
        )}>
          {output}
        </pre>
      )}
    </div>
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
                {on && <ToolRunner toolId={tool.id} />}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
