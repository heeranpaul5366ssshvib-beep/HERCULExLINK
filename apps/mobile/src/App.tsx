import { useState, useEffect, useCallback } from 'react';
import { Menu, X, Send, Paperclip, Plus, Zap, ChevronLeft, Bot, Sparkles, Shield, MessageSquare, CheckSquare, FolderKanban, Plug, Wrench, LayoutDashboard, Database, History, Clock, ArrowUpRight } from 'lucide-react';
import { cn } from '@/utils/cn';
import { MobileSidebar } from './components/MobileSidebar';
import { MobileChat } from './components/MobileChat';
import { useSystemStats } from './hooks/useSystemStats';
import { useModels } from './hooks/useModels';

function App() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [activeView, setActiveView] = useState<'home' | 'chat' | 'tasks' | 'projects' | 'memory' | 'tools' | 'plugins' | 'autonomy' | 'settings'>('home');
  const { stats, isLoading } = useSystemStats();
  const { currentModel, isModelRunning, startModel, stopModel, downloadModel, refresh: refreshModels } = useModels();

  const modelStatus = isModelRunning ? 'running' : currentModel ? 'installed' : 'not-installed';

  const handleModelStart = useCallback(async () => {
    try {
      await startModel();
    } catch (err) {
      console.error('Failed to start model:', err);
    }
  }, [startModel]);

  const handleModelStop = useCallback(async () => {
    try {
      await stopModel();
    } catch (err) {
      console.error('Failed to stop model:', err);
    }
  }, [stopModel]);

  return (
    <div className="fixed inset-0 flex flex-col bg-bg-primary text-text-primary">
      <header className="fixed top-0 left-0 right-0 z-40 h-14 bg-bg-secondary/95 backdrop-blur-sm border-b border-border-primary flex items-center px-4">
        <button
          onClick={() => setSidebarOpen(!sidebarOpen)}
          className="btn-icon p-2 lg:hidden"
          aria-label={sidebarOpen ? 'Close menu' : 'Open menu'}
        >
          {sidebarOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
        </button>
        <div className="flex-1 flex items-center justify-center">
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-blue-600 to-violet-600">
              <Bot className="w-4 h-4 text-white" />
            </div>
            <span className="font-semibold text-lg hidden sm:block">HERCULE</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className={cn(
            'flex h-2 w-2 rounded-full',
            modelStatus === 'running' ? 'bg-emerald-500 animate-pulse' : 'bg-slate-600'
          )} />
        </div>
      </header>

      <MobileSidebar
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        activeView={activeView}
        onViewChange={setActiveView}
        modelStatus={modelStatus}
        stats={stats}
        currentModel={currentModel}
      />

      <main className="flex-1 pt-14 pb-20 overflow-hidden lg:pb-0">
        <MobileChat
          activeView={activeView}
          modelStatus={modelStatus}
          currentModel={currentModel}
          onModelAction={{ 
            startModel: handleModelStart, 
            stopModel: handleModelStop, 
            installModel: () => downloadModel('hercule-base-nano') 
          }}
          stats={stats}
        />
      </main>

      <nav className="fixed bottom-0 left-0 right-0 z-40 h-16 bg-bg-secondary/95 backdrop-blur-sm border-t border-border-primary lg:hidden">
        <div className="flex h-full items-center justify-around px-2">
          {(['chat', 'tasks', 'projects', 'plugins'] as const).map((view) => (
            <button
              key={view}
              onClick={() => { setActiveView(view); setSidebarOpen(false); }}
              className={cn(
                'flex flex-col items-center gap-1 px-3 py-2 rounded-lg transition-colors',
                activeView === view
                  ? 'text-blue-400 bg-blue-500/10'
                  : 'text-text-tertiary hover:text-text-primary'
              )}
            >
              {view === 'chat' && <MessageSquare className="w-5 h-5" />}
              {view === 'tasks' && <CheckSquare className="w-5 h-5" />}
              {view === 'projects' && <FolderKanban className="w-5 h-5" />}
              {view === 'plugins' && <Plug className="w-5 h-5" />}
              <span className="text-xs font-medium">{view}</span>
            </button>
          ))}
        </div>
      </nav>
    </div>
  );
}

export { App };