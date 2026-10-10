import { useState } from 'react';
import {
  LayoutDashboard, MessageSquare, CheckSquare, FolderKanban, Database, Wrench, Plug, Zap,
  ChevronLeft, ChevronRight, Bot, Sparkles, Shield, History, Settings,
} from 'lucide-react';
import { cn } from '@/src/utils/cn';
import { useModels } from '@/src/hooks/useModels';
import { useTasks, useMemories, useProjects } from '@/src/hooks/useWorkspace';
import { useChats } from '@/src/hooks/useChats';
import type { SidebarSide } from '@/src/context/ThemeContext';

interface NavItem {
  id: string;
  label: string;
  icon: React.ReactNode;
  badge?: number;
}

const BASE_NAV_ITEMS: Omit<NavItem, 'badge'>[] = [
  { id: 'home', label: 'Home', icon: <LayoutDashboard className="w-5 h-5" /> },
  { id: 'chat', label: 'Chat', icon: <MessageSquare className="w-5 h-5" /> },
  { id: 'tasks', label: 'Tasks', icon: <CheckSquare className="w-5 h-5" /> },
  { id: 'projects', label: 'Projects', icon: <FolderKanban className="w-5 h-5" /> },
  { id: 'memory', label: 'Memory', icon: <Database className="w-5 h-5" /> },
  { id: 'tools', label: 'Tools', icon: <Wrench className="w-5 h-5" /> },
  { id: 'plugins', label: 'Plugins', icon: <Plug className="w-5 h-5" /> },
  { id: 'autonomy', label: 'Autonomy', icon: <Zap className="w-5 h-5" /> },
  { id: 'settings', label: 'Settings', icon: <Settings className="w-5 h-5" /> },
];

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
  activeView: string;
  onViewChange: (view: string) => void;
  modelStatus: string;
  updaterStatus: string;
  side?: SidebarSide;
}

export function Sidebar({
  collapsed,
  onToggle,
  activeView,
  onViewChange,
  modelStatus,
  updaterStatus,
  side = 'left',
}: SidebarProps) {
  void modelStatus;
  void updaterStatus;
  const [recentOpen, setRecentOpen] = useState(true);
  const { currentModel, isDownloading, downloadProgress } = useModels();
  const { openCount: openTasks } = useTasks();
  const { memories } = useMemories();
  const { projects } = useProjects();
  const { sessions, setActiveId, newChat } = useChats();

  const NAV_ITEMS: NavItem[] = BASE_NAV_ITEMS.map((item) =>
    item.id === 'tasks' && openTasks > 0 ? { ...item, badge: openTasks } : item
  );

  const recentItems = [
    ...sessions.slice(0, 3).map((s) => ({ id: `chat-${s.id}`, label: s.title, icon: <MessageSquare className="w-4 h-4" />, view: 'chat', time: '', chatId: s.id as string | undefined })),
    ...(projects[0] ? [{ id: `proj-${projects[0].id}`, label: projects[0].name, icon: <FolderKanban className="w-4 h-4" />, view: 'projects', time: 'recent', chatId: undefined as string | undefined }] : []),
    ...(openTasks > 0 ? [{ id: 'tasks-open', label: `${openTasks} open tasks`, icon: <CheckSquare className="w-4 h-4" />, view: 'tasks', time: 'now', chatId: undefined as string | undefined }] : []),
    { id: 'chat-new', label: 'New chat', icon: <MessageSquare className="w-4 h-4" />, view: 'chat', time: '', chatId: undefined as string | undefined, fresh: true },
    ...(memories[0] ? [{ id: `mem-${memories[0].id}`, label: memories[0].title, icon: <Database className="w-4 h-4" />, view: 'memory', time: '', chatId: undefined as string | undefined }] : []),
  ].slice(0, 4);

  const handleRecent = (item: { view: string; chatId?: string; fresh?: boolean }) => {
    if (item.fresh) newChat(null);
    else if (item.chatId) setActiveId(item.chatId);
    onViewChange(item.view);
  };

  return (
    <aside
      className={cn(
        'flex flex-col bg-bg-secondary border-border-primary transition-all duration-300 ease-out',
        'relative overflow-hidden',
        side === 'left' ? 'border-r' : 'border-l',
        collapsed ? 'w-16' : 'w-72'
      )}
      style={{ minWidth: collapsed ? '64px' : '288px' }}
    >
      <div className="flex h-16 items-center justify-between px-4 border-b border-border-primary">
        {!collapsed && (
          <div className="flex items-center gap-3">
            <div className="relative flex h-8 w-8 items-center justify-center rounded-lg t-accent-gradient text-white" style={{ boxShadow: '0 0 20px var(--theme-accent-glow)' }}>
              <Bot className="w-5 h-5 text-white" />
              <span className="absolute -top-1 -right-1 flex h-3 w-3 items-center justify-center rounded-full bg-emerald-500 animate-pulse" />
            </div>
            <span className="font-semibold text-lg text-text-primary tracking-tight">HERCULE</span>
          </div>
        )}
        <button
          onClick={onToggle}
          className={cn(
            'flex h-8 w-8 items-center justify-center rounded-lg text-text-tertiary hover:text-text-primary hover:bg-bg-tertiary transition-colors',
            collapsed && 'ml-auto'
          )}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? <ChevronRight className="w-5 h-5" /> : <ChevronLeft className="w-5 h-5" />}
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-1" role="navigation" aria-label="Main navigation">
        {NAV_ITEMS.map((item) => {
          const isActive = activeView === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onViewChange(item.id)}
              className={cn(
                'flex w-full items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200',
                'relative overflow-hidden',
                isActive
                  ? 't-nav-active'
                  : 'text-text-secondary hover:text-text-primary hover:bg-bg-tertiary border border-transparent',
                collapsed && 'justify-center px-0'
              )}
              title={collapsed ? item.label : undefined}
              aria-current={isActive ? 'page' : undefined}
            >
              <span className="flex-shrink-0">{item.icon}</span>
              {!collapsed && (
                <>
                  <span className="flex-1 truncate">{item.label}</span>
                  {item.badge && (
                    <span className="flex h-5 min-w-[18px] items-center justify-center px-1.5 text-xs font-medium bg-slate-700 text-slate-300 rounded-full">
                      {item.badge}
                    </span>
                  )}
                </>
              )}
            </button>
          );
        })}

        {!collapsed && (
          <div className="pt-6 mt-4 border-t border-border-primary">
            <div className="flex items-center justify-between px-3 mb-3">
              <h3 className="text-xs font-semibold text-text-tertiary uppercase tracking-wider flex items-center gap-2">
                <History className="w-3 h-3" />
                Recent
              </h3>
              <button
                onClick={() => setRecentOpen(!recentOpen)}
                className="text-text-tertiary hover:text-text-primary transition-colors p-1"
                aria-label={recentOpen ? 'Collapse recent' : 'Expand recent'}
              >
                {recentOpen ? (
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" /></svg>
                ) : (
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
                )}
              </button>
            </div>
            <div className={cn('transition-all duration-200 ease-out overflow-hidden', recentOpen ? 'max-h-64 opacity-100' : 'max-h-0 opacity-0')}>
              {recentItems.length === 0 && (
                <p className="px-3 py-2 text-xs text-text-muted">Nothing yet — your activity will appear here.</p>
              )}
              {recentItems.map((item) => (
                <button
                  key={item.id}
                  onClick={() => handleRecent(item)}
                  className={cn(
                    'flex w-full items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors',
                    'text-text-tertiary hover:text-text-primary hover:bg-bg-tertiary'
                  )}
                >
                  <span className="flex-shrink-0 text-text-muted">{item.icon}</span>
                  <span className="truncate flex-1 text-left">{item.label}</span>
                  {item.time && <span className="text-xs text-text-muted">{item.time}</span>}
                </button>
              ))}
            </div>
          </div>
        )}
      </nav>

      <div className="p-3 border-t border-border-primary">
        {!collapsed ? (
          <div className="relative rounded-xl t-accent-bg-soft t-accent-border border p-4 overflow-hidden">
            <div className="relative flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl t-accent-bg-soft backdrop-blur-sm border t-accent-border">
                <Sparkles className="w-5 h-5 t-accent-text" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="font-semibold text-text-primary truncate">HERCULE</p>
                <p className="text-xs text-text-tertiary truncate">Your local AI assistant</p>
              </div>
            </div>
            <div className="mt-3 flex items-center gap-2 text-xs text-text-tertiary">
              <Shield className="w-3 h-3" />
              <span>Local-first</span>
              <span className="w-px h-4 bg-slate-600" />
              <span>Private</span>
              <span className="w-px h-4 bg-slate-600" />
              <span>Offline</span>
            </div>
            {currentModel && (
              <div className="mt-3 pt-3 border-t border-border-primary flex items-center justify-between text-xs">
                <span className="text-text-tertiary flex items-center gap-1 min-w-0">
                  <Bot className="w-3 h-3 flex-shrink-0" />
                  <span className="truncate">Model: {currentModel}</span>
                </span>
                {isDownloading && (
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <div className="w-20 h-1.5 bg-slate-700 rounded-full overflow-hidden">
                      <div
                        className="h-full t-accent-gradient transition-all duration-300"
                        style={{ width: `${downloadProgress}%` }}
                      />
                    </div>
                    <span className="t-accent-text font-mono">{downloadProgress}%</span>
                  </div>
                )}
              </div>
            )}
          </div>
        ) : (
          <div className="relative rounded-xl t-accent-bg-soft border t-accent-border p-3 overflow-hidden mx-auto" style={{ width: '40px' }}>
            <div className="flex h-10 w-10 items-center justify-center rounded-xl t-accent-bg-soft backdrop-blur-sm border t-accent-border mx-auto">
              <Sparkles className="w-5 h-5 t-accent-text" />
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}
