import { useState, useCallback, useEffect, useRef } from 'react';
import { Sidebar } from './components/sidebar/Sidebar';
import { MainContent } from './components/layout/MainContent';
import { RightPanel } from './components/panels/RightPanel';
import { ErrorBoundary } from './components/layout/ErrorBoundary';
import { ThemeProvider, useTheme } from './context/ThemeContext';
import { useSystemStats } from './hooks/useSystemStats';
import { useModels } from './hooks/useModels';
import { useUpdater } from './hooks/useUpdater';
import { useAppConfig } from './hooks/useAppConfig';
import { IDLE_STOP_MINUTES, LAST_CHAT_KEY, IDLE_STOP_KEY } from './constants';
import { cn } from './utils/cn';

export type AppView = 'home' | 'chat' | 'tasks' | 'projects' | 'memory' | 'tools' | 'plugins' | 'autonomy' | 'settings';

function Shell() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [activeView, setActiveView] = useState<AppView>('home');
  const { stats, isLoading } = useSystemStats();
  const { currentModel, running, startModel, stopModel, downloadModel, autoRoute, routeFor, selectModel } = useModels();
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

  // v2.2: auto-route a message to the best installed model before sending.
  // Returns a human note when it switched models, null when it stayed.
  const handleRouteMessage = useCallback(async (text: string): Promise<string | null> => {
    if (!autoRoute) return null;
    try {
      if (typeof window === 'undefined' || !window.electronAPI) return null;
      const r = await routeFor(text);
      if (r.model !== currentModel) {
        await selectModel(r.model);
        await startModel(r.model);
        return `Routed to ${r.model} — ${r.reason}`;
      }
    } catch (err) {
      console.error('Auto-route failed, using active model:', err);
    }
    return null;
  }, [autoRoute, currentModel, routeFor, selectModel, startModel]);

  const { sidebarSide, showRightPanel, bgEffect } = useTheme();

  const sidebar = (
    <ErrorBoundary area="the sidebar">
      <Sidebar
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
        activeView={activeView}
        onViewChange={(v) => setActiveView(v as AppView)}
        modelStatus={modelStatus}
        updaterStatus={updaterStatus}
        side={sidebarSide}
      />
    </ErrorBoundary>
  );

  return (
    <ErrorBoundary area="the app shell">
      <div className={cn('bg-fx flex h-screen w-screen overflow-hidden bg-bg-primary text-text-primary', `bg-fx-${bgEffect}`)}>
        {sidebarSide === 'left' && sidebar}
        <div className="flex-1 flex flex-col overflow-hidden min-w-0">
          <ErrorBoundary area="this view" key={activeView}>
            <MainContent
              activeView={activeView}
              modelStatus={modelStatus}
              currentModel={currentModel}
              onModelAction={{ startModel: handleModelStart, stopModel: handleModelStop, installModel: () => downloadModel('hercule-base-nano'), routeMessage: handleRouteMessage }}
              stats={stats}
              isLoading={isLoading}
              ctxBudget={ctxSizeEffective || 4096}
            />
          </ErrorBoundary>
        </div>
        {showRightPanel && (
          <ErrorBoundary area="the monitoring panel">
            <RightPanel stats={stats} isLoading={isLoading} modelStatus={modelStatus} currentModel={currentModel} ctxSize={ctxSizeEffective} />
          </ErrorBoundary>
        )}
        {sidebarSide === 'right' && sidebar}
      </div>
    </ErrorBoundary>
  );
}

function App() {
  return (
    <ThemeProvider>
      <Shell />
    </ThemeProvider>
  );
}

export { App };
