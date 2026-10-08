import { useState } from 'react';
import { Plug, Github, Globe, HardDrive, Monitor, Terminal, FolderSearch, CalendarDays, Mail, CheckCircle2, Plus, ShieldCheck, Trash2, X } from 'lucide-react';
import { cn } from '@/src/utils/cn';
import { usePlugins } from '@/src/hooks/useIntegrations';
import type { HerculePlugin } from '@/src/types/electron';

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
  const { plugins, enabled, toggle, connectedCount, refresh } = usePlugins();
  const [preview, setPreview] = useState<{ manifest: HerculePlugin; folder: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const hasBridge = typeof window !== 'undefined' && !!window.electronAPI?.plugins;

  const browse = async () => {
    if (!hasBridge) return;
    setError(null);
    setNotice(null);
    try {
      const paths = await window.electronAPI.dialog.openDirectory({});
      const folder = paths?.[0];
      if (!folder) return;
      setBusy(true);
      const manifest = await window.electronAPI.plugins.preview(folder);
      setPreview({ manifest, folder });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not read that plugin.');
    } finally {
      setBusy(false);
    }
  };

  const install = async () => {
    if (!preview || !hasBridge) return;
    setError(null);
    setBusy(true);
    try {
      await window.electronAPI.plugins.install(preview.folder);
      setNotice(`${preview.manifest.name} installed with ${preview.manifest.permissions.length} permission(s).`);
      setPreview(null);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Install failed.');
    } finally {
      setBusy(false);
    }
  };

  const uninstall = async (id: string, name: string) => {
    if (!hasBridge) return;
    setError(null);
    setBusy(true);
    try {
      await window.electronAPI.plugins.uninstall(id);
      setNotice(`${name} uninstalled.`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Uninstall failed.');
    } finally {
      setBusy(false);
    }
  };

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
        <button
          onClick={browse}
          disabled={!hasBridge || busy}
          className="btn-secondary px-4 py-2 text-sm rounded-lg flex items-center gap-1.5 disabled:opacity-40"
          title={hasBridge ? 'Install a community plugin from a folder' : 'Needs the desktop app'}
        >
          <Plus className="w-4 h-4" /> {busy ? '…' : 'Browse'}
        </button>
      </div>

      <p className="mt-4 text-sm text-text-tertiary">
        Connect HERCULE to the apps you already use. Connections run locally — credentials never leave this PC.
        Community plugins declare permissions up front; installing is the grant.
      </p>

      {error && (
        <p className="mt-3 rounded-lg border border-red-500/30 bg-red-500/5 px-3 py-2 text-xs text-red-300">{error}</p>
      )}
      {notice && (
        <p className="mt-3 rounded-lg border t-accent-border t-accent-bg-soft px-3 py-2 text-xs t-accent-text">{notice}</p>
      )}

      {preview && (
        <div className="card mt-3 p-4 t-accent-border animate-slide-up" role="alertdialog" aria-label="Approve plugin install">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="font-semibold text-text-primary">{preview.manifest.name} <span className="text-xs font-mono text-text-muted">v{preview.manifest.version}</span></p>
              <p className="text-xs text-text-tertiary mt-0.5">{preview.manifest.description}</p>
            </div>
            <button onClick={() => setPreview(null)} className="btn-icon p-1.5" aria-label="Cancel install">
              <X className="w-4 h-4" />
            </button>
          </div>
          <p className="mt-3 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-text-tertiary">
            <ShieldCheck className="w-3.5 h-3.5" /> Requests {preview.manifest.permissions.length} permission(s)
          </p>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {preview.manifest.permissions.length === 0 && (
              <span className="text-xs text-text-muted">None — runs fully sandboxed.</span>
            )}
            {preview.manifest.permissions.map((p) => (
              <span key={p} className="px-2 py-0.5 text-xs font-mono rounded-full border border-amber-500/30 bg-amber-500/10 text-amber-300">
                {p}
              </span>
            ))}
          </div>
          <div className="mt-3 flex gap-2">
            <button onClick={install} disabled={busy} className="btn-primary px-4 py-1.5 text-xs rounded-lg disabled:opacity-50">
              {busy ? 'Installing…' : 'Install & grant'}
            </button>
            <button onClick={() => setPreview(null)} className="btn-secondary px-4 py-1.5 text-xs rounded-lg">
              Cancel
            </button>
          </div>
        </div>
      )}

      <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
        {plugins.map((plugin) => {
          const on = !!enabled[plugin.id];
          const community = plugin.source === 'community';
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
              <h3 className="font-semibold text-text-primary flex items-center gap-2 flex-wrap">
                {plugin.name}
                {community && (
                  <span className="px-2 py-0.5 text-[11px] font-medium rounded-full bg-violet-500/15 text-violet-300 border border-violet-500/20">
                    Community
                  </span>
                )}
              </h3>
              <p className="text-xs text-text-muted mb-1">{plugin.category}{plugin.version && plugin.version !== 'built-in' ? ` • v${plugin.version}` : ''}</p>
              <p className="text-sm text-text-tertiary flex-1">{plugin.description}</p>
              {plugin.permissions.length > 0 && (
                <p className="mt-1.5 flex items-center gap-1 text-[11px] font-mono text-text-muted">
                  <ShieldCheck className="w-3 h-3 flex-shrink-0" /> {plugin.permissions.join(', ')}
                </p>
              )}
              <div className="mt-3 flex gap-2">
                <button
                  onClick={() => toggle(plugin.id)}
                  className={cn(
                    'flex-1 px-3 py-1.5 text-sm font-medium rounded-lg border transition-all',
                    on
                      ? 'text-text-tertiary border-border-primary hover:text-red-400 hover:border-red-500/30'
                      : 't-accent-bg-soft t-accent-text t-accent-border hover:brightness-110'
                  )}
                >
                  {on ? 'Disconnect' : 'Connect'}
                </button>
                {community && (
                  <button
                    onClick={() => uninstall(plugin.id, plugin.name)}
                    disabled={busy}
                    className="btn-icon p-1.5 text-text-tertiary hover:text-red-400 hover:bg-red-500/10 rounded-lg disabled:opacity-40"
                    title={`Uninstall ${plugin.name}`}
                    aria-label={`Uninstall ${plugin.name}`}
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
