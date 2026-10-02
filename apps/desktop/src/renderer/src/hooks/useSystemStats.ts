import { useState, useEffect, useCallback, useRef } from 'react';

interface SystemStats {
  cpu: number;
  ram: number;
  storage: number;
  gpu: number;
}

export function useSystemStats() {
  const [stats, setStats] = useState<SystemStats>({ cpu: 0, ram: 0, storage: 0, gpu: 0 });
  const [isLoading, setIsLoading] = useState(true);
  const inFlight = useRef(false);

  const fetchStats = useCallback(async () => {
    if (inFlight.current) return;
    if (typeof document !== 'undefined' && document.hidden) return;
    inFlight.current = true;
    try {
      if (window.electronAPI) {
        const data = await window.electronAPI.system.getStats();
        setStats(data);
      } else {
        setStats({
          cpu: Math.floor(Math.random() * 30) + 5,
          ram: Math.floor(Math.random() * 40) + 20,
          storage: Math.floor(Math.random() * 50) + 30,
          gpu: Math.floor(Math.random() * 20),
        });
      }
    } catch (err) {
      console.error('Failed to fetch system stats:', err);
    } finally {
      inFlight.current = false;
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStats();
    const interval = setInterval(fetchStats, 10000);
    return () => clearInterval(interval);
  }, [fetchStats]);

  useEffect(() => {
    if (!window.electronAPI) return;
    const unsubscribe = window.electronAPI.system.onStatsUpdate((newStats: SystemStats) => {
      setStats(newStats);
    });
    return unsubscribe;
  }, []);

  return { stats, isLoading, refresh: fetchStats };
}