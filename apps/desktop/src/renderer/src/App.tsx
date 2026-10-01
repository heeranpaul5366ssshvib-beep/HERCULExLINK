import { useState, useCallback, useEffect, useRef } from 'react';
import { Sidebar } from './components/sidebar/Sidebar';
import { MainContent } from './components/layout/MainContent';
import { RightPanel } from './components/panels/RightPanel';
import { ErrorBoundary } from './components/layout/ErrorBoundary';
import { ThemeProvider } from './context/ThemeContext';
import { useSystemStats } from './hooks/useSystemStats';
import { useModels } from './hooks/useModels';
import { useUpdater } from './hooks/useUpdater';
import { useAppConfig } from './hooks/useAppConfig';
import { IDLE_STOP_MINUTES, LAST_CHAT_KEY, IDLE_STOP_KEY } from './constants';

export type AppView = 'home' | 'chat' | 'tasks' | 'projects' | 'memory' | 'tools' | 'plugins' | 'autonomy' | 'settings';

function App() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [activeView, setActiveView] = useState<AppView>('home');
  const { stats, isLoading } = useSystemStats();
  const { currentModel, running, startModel, stopModel, downloadModel } = useModels();
  const { status: updaterStatus } = useUpdater();
  const { num: configNum } = useAppConfig(15000);

  const modelStatus = running ? 'running' : currentModel ? 'installed' : 'not-installed';
  const ctxSizeEffective = configNum('ctxSizeEffective', 0);

  // Idle auto-stop: free all model RAM after 15 idle minutes (toggle in Settings).
  const runningRef = useRef(running);
  runningRef.current = running;
  const stopRef = useRef(stopModel);
  stopRef.current = stopModel;
  useEffect(() => {
    const id = setInterval(async () => {
      try {
        const raw = localStorage.getItem(IDLE_STOP_KEY);
        if (raw !== '1' && raw !== 'true') return;
        if (!runningRef.current) return;
        const last = parseInt(localStorage.getItem(LAST_CHAT_KEY) || '0', 10);
        if (!last || Date.now() - last < IDLE_STOP_MINUTES * 60 * 1000) return;
        await stopRef.current();
      } catch {
        // never let the watchdog crash the app
      }
    }, 60000);
    return () => clearInterval(id);
  }, []);

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
    <ThemeProvider>
      <ErrorBoundary area="the app shell">
        <div className="flex h-screen w-screen overflow-hidden bg-bg-primary text-text-primary">
          <ErrorBoundary area="the sidebar">
            <Sidebar
              collapsed={sidebarCollapsed}
              onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
              activeView={activeView}
              onViewChange={(v) => setActiveView(v as AppView)}
              modelStatus={modelStatus}
              updaterStatus={updaterStatus}
            />
          </ErrorBoundary>
          <div className="flex-1 flex flex-col overflow-hidden">
            <ErrorBoundary area="this view" key={activeView}>
              <MainContent
                activeView={activeView}
                modelStatus={modelStatus}
                currentModel={currentModel}
                onModelAction={{ startModel: handleModelStart, stopModel: handleModelStop, installModel: () => downloadModel('hercule-base-nano') }}
                stats={stats}
                isLoading={isLoading}
              />
            </ErrorBoundary>
          </div>
          <ErrorBoundary area="the monitoring panel">
            <RightPanel stats={stats} isLoading={isLoading} modelStatus={modelStatus} currentModel={currentModel} ctxSize={ctxSizeEffective} />
          </ErrorBoundary>
        </div>
      </ErrorBoundary>
    </ThemeProvider>
  );
}

export { App };
