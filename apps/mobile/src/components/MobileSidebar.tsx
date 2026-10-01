import { cn } from '@/utils/cn';
import { X, LayoutDashboard, MessageSquare, CheckSquare, FolderKanban, Database, Wrench, Plug, Zap, Bot, Sparkles, Shield, ChevronRight, History, Clock } from 'lucide-react';

interface MobileSidebarProps {
  isOpen: boolean;
  onClose: () => void;
  activeView: string;
  onViewChange: (view: string) => void;
  modelStatus: string;
  stats: { cpu: number; ram: number; storage: number; gpu: number };
  currentModel: string | null;
}

const NAV_ITEMS = [
  { id: 'home', label: 'Home', icon: LayoutDashboard },
  { id: 'chat', label: 'Chat', icon: MessageSquare },
  { id: 'tasks', label: 'Tasks', icon: CheckSquare, badge: 3 },
  { id: 'projects', label: 'Projects', icon: FolderKanban },
  { id: 'memory', label: 'Memory', icon: Database },
  { id: 'tools', label: 'Tools', icon: Wrench },
  { id: 'plugins', label: 'Plugins', icon: Plug },
  { id: 'autonomy', label: 'Autonomy', icon: Zap },
  { id: 'settings', label: 'Settings', icon: Wrench },
];

const RECENT_ITEMS = [
  { id: '1', label: 'Project Alpha', icon: FolderKanban, time: '2h ago' },
  { id: '2', label: 'Task: Refactor API', icon: CheckSquare, time: '5h ago' },
  { id: '3', label: 'Chat: Architecture', icon: MessageSquare, time: '1d ago' },
  { id: '4', label: 'Memory: User prefs', icon: Database, time: '3d ago' },
];

export function MobileSidebar({ isOpen, onClose, activeView, onViewChange, modelStatus, stats, currentModel }: MobileSidebarProps) {
  return (
    <>
      {isOpen && (
        <div
          className="fixed inset-0 z-50 bg-black/50 lg:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}
      <aside
        className={cn(
          'fixed top-0 left-0 z-50 h-full w-72 bg-bg-secondary border-r border-border-primary transform transition-transform duration-300 ease-out lg:relative lg:translate-x-0 lg:z-auto flex flex-col',
          isOpen ? 'translate-x-0' : '-translate-x-full'
        )}
        aria-label="Sidebar navigation"
      >
        <div className="flex h-14 items-center justify-between px-4 border-b border-border-primary">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-blue-600 to-violet-600">
              <Bot className="w-5 h-5 text-white" />
            </div>
            <span className="font-semibold text-lg">HERCULE</span>
          </div>
          <button onClick={onClose} className="btn-icon p-2 lg:hidden" aria-label="Close sidebar">
            <X className="w-5 h-5" />
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-1">
          {NAV_ITEMS.map((item) => {
            const isActive = activeView === item.id;
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                onClick={() => { onViewChange(item.id); onClose(); }}
                className={cn(
                  'flex w-full items-center gap-3 px-3 py-3 rounded-lg text-base font-medium transition-all duration-200',
                  isActive
                    ? 'bg-blue-600/20 text-blue-400 border border-blue-500/20'
                    : 'text-text-secondary hover:text-text-primary hover:bg-bg-tertiary'
                )}
              >
                <Icon className="w-5 h-5 flex-shrink-0" />
                <span className="flex-1 truncate">{item.label}</span>
                {item.badge && (
                  <span className="flex h-5 min-w-[18px] items-center justify-center px-1.5 text-xs font-medium bg-slate-700 text-slate-300 rounded-full">
                    {item.badge}
                  </span>
                )}
                <ChevronRight className="ml-auto w-4 h-4 text-text-muted" />
              </button>
            );
          })}

          <div className="pt-6 mt-4 border-t border-border-primary">
            <h3 className="px-3 mb-3 text-xs font-semibold text-text-tertiary uppercase tracking-wider flex items-center gap-2">
              <History className="w-3 h-3" />
              Recent
            </h3>
            {RECENT_ITEMS.map((item) => (
              <button
                key={item.id}
                onClick={onClose}
                className={cn(
                  'flex w-full items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors',
                  'text-text-tertiary hover:text-text-primary hover:bg-bg-tertiary'
                )}
              >
                <span className="flex-shrink-0 text-text-muted"><item.icon className="w-4 h-4" /></span>
                <span className="truncate flex-1">{item.label}</span>
                <span className="text-xs text-text-muted">{item.time}</span>
              </button>
            ))}
          </div>
        </nav>

        <div className="p-4 border-t border-border-primary space-y-4">
          <div className="relative rounded-xl bg-gradient-to-br from-blue-600/20 to-violet-600/20 border border-blue-500/30 p-4 overflow-hidden">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-600/30 backdrop-blur-sm border border-blue-500/30">
                <Sparkles className="w-5 h-5 text-blue-300" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="font-semibold text-text-primary truncate">HERCULE</p>
                <p className="text-xs text-blue-300/80 truncate">Your local AI assistant</p>
              </div>
            </div>
            <div className="mt-3 flex flex-wrap gap-2 text-xs text-blue-300/70">
              <span className="flex items-center gap-1"><Shield className="w-3 h-3" /> Local-first</span>
              <span className="flex items-center gap-1"><Shield className="w-3 h-3" /> Private</span>
              <span className="flex items-center gap-1"><Shield className="w-3 h-3" /> Offline</span>
            </div>
            {currentModel && (
              <div className="mt-3 pt-3 border-t border-blue-500/20 flex items-center justify-between text-xs">
                <span className="text-blue-300/70 flex items-center gap-1">
                  <Bot className="w-3 h-3" />
                  Model: {currentModel}
                </span>
                <span className={cn(
                  'flex h-2 w-2 rounded-full',
                  modelStatus === 'running' ? 'bg-emerald-500 animate-pulse' : 'bg-amber-500'
                )} />
              </div>
            )}
          </div>

          <div className="rounded-xl bg-slate-800/50 border border-border-primary p-4">
            <h3 className="font-medium mb-3 flex items-center gap-2">
              <Clock className="w-4 h-4 text-text-tertiary" />
              System
            </h3>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <p className="text-text-tertiary">CPU</p>
                <p className="font-mono font-semibold">{stats.cpu}%</p>
              </div>
              <div>
                <p className="text-text-tertiary">RAM</p>
                <p className="font-mono font-semibold">{stats.ram}%</p>
              </div>
              <div>
                <p className="text-text-tertiary">Storage</p>
                <p className="font-mono font-semibold">{stats.storage}%</p>
              </div>
              <div>
                <p className="text-text-tertiary">GPU</p>
                <p className="font-mono font-semibold">{stats.gpu}%</p>
              </div>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}