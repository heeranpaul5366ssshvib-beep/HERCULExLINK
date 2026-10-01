import { useState, useEffect, useRef } from 'react';
import { Bot, Check, Download, Trash2, ChevronDown, ExternalLink, Sparkles, Loader2, Play, Square, Zap } from 'lucide-react';
import { cn } from '@/src/utils/cn';
import { useModels } from '@/src/hooks/useModels';

interface ModelSelectorProps {
  currentStatus: string;
  onClick?: () => void;
  compact?: boolean;
}

export function ModelSelector({ currentStatus, onClick, compact = false }: ModelSelectorProps) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [llamaStatus, setLlamaStatus] = useState<{ found: boolean; path: string; bundled: boolean } | null>(null);
  const [installingLlama, setInstallingLlama] = useState(false);
  const {
    availableModels,
    installedModels,
    currentModel,
    running,
    starting,
    isDownloading,
    downloadProgress,
    downloadingModel,
    downloadModel,
    deleteModel,
    selectModel,
    startModel,
    stopModel,
    refresh,
  } = useModels();

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  useEffect(() => {
    if (!isOpen || !window.electronAPI) return;
    window.electronAPI.system.getLlamaStatus().then(setLlamaStatus).catch(() => setLlamaStatus(null));
  }, [isOpen]);

  const handleInstallLlama = async () => {
    if (!window.electronAPI) return;
    setInstallingLlama(true);
    setActionError(null);
    try {
      const status = await window.electronAPI.system.installLlama();
      setLlamaStatus(status);
      if (!status.found) {
        setActionError('llama.cpp is still not available. Install it from https://github.com/ggerganov/llama.cpp/releases and restart HERCULE.');
      }
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Engine installation failed.');
    } finally {
      setInstallingLlama(false);
    }
  };

  const handleModelAction = async (modelName: string, action: 'download' | 'select' | 'delete' | 'start' | 'stop') => {
    setActionError(null);
    try {
      if (action === 'download') {
        await downloadModel(modelName);
        setIsOpen(false);
      } else if (action === 'select') {
        await selectModel(modelName);
        refresh();
      } else if (action === 'start') {
        await selectModel(modelName);
        await startModel();
        setIsOpen(false);
      } else if (action === 'stop') {
        await stopModel();
      } else if (action === 'delete') {
        if (currentModel === modelName && running) {
          await stopModel();
        }
        await deleteModel(modelName);
        refresh();
      }
    } catch (err) {
      console.error(`Failed to ${action} model:`, err);
      setActionError(err instanceof Error ? err.message : `Failed to ${action} model.`);
    }
  };

  const isModelInstalled = (name: string) => installedModels.some(m => m.startsWith(name));
  const isCurrentModel = (name: string) => currentModel === name;

  if (compact) {
    return (
      <button
        onClick={onClick}
        className={cn(
          'flex items-center gap-1.5 px-2 py-1 text-xs font-medium rounded-full transition-colors',
          currentStatus === 'running'
            ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/20'
            : currentStatus === 'not-installed'
            ? 'bg-amber-500/15 text-amber-400 border border-amber-500/20'
            : 'bg-slate-700/50 text-text-tertiary border border-border-primary'
        )}
      >
        <span className={cn('w-1.5 h-1.5 rounded-full', currentStatus === 'running' ? 'bg-emerald-500 animate-pulse' : 'bg-amber-500 animate-pulse')} />
        {currentStatus === 'running' ? 'Model Running' : currentStatus === 'not-installed' ? 'No Model' : 'Model Ready'}
        <ChevronDown className="w-3 h-3" />
      </button>
    );
  }

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          'flex items-center gap-2 px-3 py-1.5 text-sm font-medium rounded-lg transition-colors',
          'bg-slate-800/50 text-text-secondary border border-border-primary hover:bg-slate-800 hover:text-text-primary'
        )}
      >
        <Bot className="w-4 h-4 text-blue-400" />
        <span className="hidden sm:inline">Model</span>
        <ChevronDown className={cn('w-4 h-4 transition-transform', isOpen && 'rotate-180')} />
      </button>

      {isOpen && (
        <div className="absolute right-0 bottom-full mb-2 w-80 bg-bg-secondary border border-border-primary rounded-xl shadow-lg overflow-hidden animate-slide-up z-50">
          <div className="p-4 border-b border-border-primary flex items-center justify-between">
            <h3 className="font-semibold text-text-primary flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-blue-400" />
              Model Manager
            </h3>
            <button
              onClick={() => setIsOpen(false)}
              className="p-1 text-text-tertiary hover:text-text-primary rounded-lg hover:bg-bg-tertiary"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
            </button>
          </div>

          {starting && (
            <div className="px-4 py-2.5 flex items-center gap-2 text-xs text-blue-300 bg-blue-500/10 border-b border-blue-500/20">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              <span>{running ? 'Stopping model server…' : 'Starting model server (this can take a minute)…'}</span>
            </div>
          )}
          {actionError && (
            <div className="px-4 py-2.5 text-xs text-red-300 bg-red-500/10 border-b border-red-500/20">
              {actionError}
            </div>
          )}

          <div className="px-4 py-2.5 flex items-center gap-2 border-b border-border-primary bg-slate-900/30">
            <div className={cn(
              'flex h-7 w-7 items-center justify-center rounded-lg flex-shrink-0',
              llamaStatus?.found ? 'bg-emerald-500/15 text-emerald-400' : 'bg-amber-500/15 text-amber-400'
            )}>
              <Zap className="w-3.5 h-3.5" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium text-text-primary">Inference engine</p>
              <p className="text-[11px] text-text-tertiary truncate">
                {llamaStatus == null
                  ? 'Checking…'
                  : llamaStatus.found
                    ? llamaStatus.bundled
                      ? 'llama.cpp bundled with HERCULE ✓'
                      : 'llama.cpp found on system ✓'
                    : 'llama.cpp missing — models cannot start'}
              </p>
            </div>
            {llamaStatus && !llamaStatus.found && (
              <button
                onClick={handleInstallLlama}
                disabled={installingLlama}
                className="btn-primary text-xs px-3 py-1.5 flex-shrink-0 flex items-center gap-1.5 disabled:opacity-50"
              >
                {installingLlama ? <Loader2 className="w-3 h-3 animate-spin" /> : <Download className="w-3 h-3" />}
                {installingLlama ? 'Installing…' : 'Install'}
              </button>
            )}
          </div>

          <div className="max-h-96 overflow-y-auto p-3 space-y-2">
            {availableModels.map((model) => {
              const installed = isModelInstalled(model.name);
              const current = isCurrentModel(model.name);
              const downloading = isDownloading && downloadingModel === model.name;

              return (
                <div key={model.name} className={cn(
                  'p-3 rounded-lg border transition-all',
                  current ? 'border-blue-500/30 bg-blue-500/5' : 'border-border-primary hover:border-border-secondary'
                )}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <Bot className={cn('w-4 h-4', current ? 'text-blue-400' : 'text-text-tertiary')} />
                        <span className="font-medium text-text-primary truncate">{model.name}</span>
                        {current && (
                          <span className="flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full bg-blue-500/15 text-blue-400 border border-blue-500/20">
                            <Check className="w-3 h-3" />
                            Active
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-text-tertiary truncate">{model.description}</p>
                      <div className="mt-1 flex items-center gap-2 text-xs text-text-muted">
                        <span>v{model.version}</span>
                        <span>•</span>
                        <span>~{(model.size / 1e9).toFixed(1)} GB</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      {downloading ? (
                        <div className="flex items-center gap-2 w-32">
                          <div className="flex-1 h-1.5 bg-slate-700 rounded-full overflow-hidden">
                            <div
                              className="h-full bg-gradient-to-r from-blue-500 to-violet-500 transition-all duration-300"
                              style={{ width: `${downloadProgress}%` }}
                            />
                          </div>
                          <span className="text-xs font-mono text-blue-400 w-10 text-right">{downloadProgress}%</span>
                        </div>
                      ) : installed ? (
                        <div className="flex items-center gap-1.5 flex-shrink-0">
                          {current && running ? (
                            <button
                              onClick={() => handleModelAction(model.name, 'stop')}
                              disabled={starting}
                              className="btn-icon p-1.5 text-emerald-400 hover:bg-emerald-500/10 rounded-lg disabled:opacity-50 disabled:cursor-wait"
                              title="Stop model server"
                            >
                              {starting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Square className="w-4 h-4" />}
                            </button>
                          ) : (
                            <button
                              onClick={() => handleModelAction(model.name, 'start')}
                              disabled={starting || isDownloading}
                              className="btn-icon p-1.5 text-blue-400 hover:bg-blue-500/10 rounded-lg disabled:opacity-50 disabled:cursor-wait"
                              title={current ? 'Start model server' : 'Select and start this model'}
                            >
                              {starting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                            </button>
                          )}
                          {!current && (
                            <button
                              onClick={() => handleModelAction(model.name, 'select')}
                              disabled={starting}
                              className="btn-icon p-1.5 text-text-tertiary hover:text-text-primary hover:bg-bg-tertiary rounded-lg disabled:opacity-50"
                              title="Select without starting"
                            >
                              <Check className="w-4 h-4" />
                            </button>
                          )}
                          <button
                            onClick={() => handleModelAction(model.name, 'delete')}
                            disabled={starting || isDownloading}
                            className="btn-icon p-1.5 text-text-tertiary hover:text-red-400 hover:bg-red-500/10 rounded-lg disabled:opacity-50"
                            title="Delete model"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={() => handleModelAction(model.name, 'download')}
                          className="btn-primary text-xs px-3 py-1.5 flex items-center gap-1.5"
                        >
                          <Download className="w-3 h-3" />
                          Download
                        </button>
                      )}
                    </div>
                  </div>
                  {model.quantizations.length > 0 && (
                    <div className="mt-2 pt-2 border-t border-border-primary flex flex-wrap gap-1">
                      {model.quantizations.map((q) => (
                        <span key={q} className="px-2 py-0.5 text-xs font-mono rounded bg-slate-800 text-text-tertiary border border-border-primary">
                          {q}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}

            {availableModels.length === 0 && (
              <div className="text-center py-8 text-text-tertiary">
                <Bot className="w-8 h-8 mx-auto mb-2 text-text-muted" />
                <p>No models available</p>
                <p className="text-xs mt-1">Check your internet connection</p>
              </div>
            )}
          </div>

          <div className="p-3 border-t border-border-primary bg-slate-900/30">
            <div className="flex items-center justify-between text-xs text-text-tertiary">
              <span>Models stored locally • Private & offline</span>
              <a
                href="https://huggingface.co/HeeranPaul"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 hover:text-blue-400 transition-colors"
                onClick={(e) => e.stopPropagation()}
              >
                <ExternalLink className="w-3 h-3" />
                Browse Models
              </a>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}