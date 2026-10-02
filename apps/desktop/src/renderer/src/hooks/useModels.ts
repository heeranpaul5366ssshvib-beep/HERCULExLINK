import { useState, useEffect, useCallback } from 'react';

interface ModelInfo {
  name: string;
  version: string;
  url: string;
  size: number;
  sha256: string;
  description: string;
  quantizations: string[];
  kind?: 'gguf' | 'nano';
  checkpointDir?: string;
  tokenizerDir?: string;
  experimental?: boolean;
}

interface DownloadProgress {
  modelName: string;
  progress: number;
  downloaded: number;
  total: number;
}

export function useModels() {
  const [availableModels, setAvailableModels] = useState<ModelInfo[]>([]);
  const [installedModels, setInstalledModels] = useState<string[]>([]);
  const [currentModel, setCurrentModel] = useState<string | null>(null);
  const [isDownloading, setIsDownloading] = useState(false);
  const [downloadProgress, setDownloadProgress] = useState(0);
  const [downloadingModel, setDownloadingModel] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [starting, setStarting] = useState(false);

  const fetchAvailableModels = useCallback(async () => {
    try {
      if (window.electronAPI) {
        const models = await window.electronAPI.models.getAvailable();
        setAvailableModels(models);
      }
    } catch (err) {
      console.error('Failed to fetch available models:', err);
    }
  }, []);

  const fetchInstalledModels = useCallback(async () => {
    try {
      if (window.electronAPI) {
        const models = await window.electronAPI.models.getInstalled();
        setInstalledModels(models);
      }
    } catch (err) {
      console.error('Failed to fetch installed models:', err);
    }
  }, []);

  const fetchCurrentModel = useCallback(async () => {
    try {
      if (window.electronAPI) {
        const model = await window.electronAPI.models.getCurrent();
        setCurrentModel(model);
      }
    } catch (err) {
      console.error('Failed to fetch current model:', err);
    }
  }, []);

  useEffect(() => {
    fetchAvailableModels();
    fetchInstalledModels();
    fetchCurrentModel();

    if (!window.electronAPI) return;
    const unsubscribe = window.electronAPI.models.onDownloadProgress((progress: DownloadProgress) => {
      setIsDownloading(true);
      setDownloadingModel(progress.modelName);
      setDownloadProgress(progress.progress);
      if (progress.progress >= 100) {
        setIsDownloading(false);
        setDownloadingModel(null);
        fetchInstalledModels();
        fetchCurrentModel();
      }
    });
    return unsubscribe;
  }, [fetchAvailableModels, fetchInstalledModels, fetchCurrentModel]);

  const downloadModel = useCallback(async (modelName: string, quantization: string = 'q4_k_m') => {
    setError(null);
    try {
      if (window.electronAPI) {
        await window.electronAPI.models.download(modelName, quantization);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Download failed');
      setIsDownloading(false);
      setDownloadingModel(null);
      throw err;
    }
  }, []);

  const deleteModel = useCallback(async (modelName: string) => {
    try {
      if (window.electronAPI) {
        await window.electronAPI.models.delete(modelName);
        fetchInstalledModels();
        if (currentModel === modelName) {
          setCurrentModel(null);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed');
      throw err;
    }
  }, [currentModel, fetchInstalledModels]);

  const selectModel = useCallback(async (modelName: string) => {
    try {
      if (window.electronAPI) {
        await window.electronAPI.models.setCurrent(modelName);
        setCurrentModel(modelName);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to select model');
      throw err;
    }
  }, []);

  const refreshRunning = useCallback(async () => {
    try {
      if (window.electronAPI) {
        setRunning(await window.electronAPI.models.isRunning());
      }
    } catch {
      // Leave last known state on transient IPC errors.
    }
  }, []);

  useEffect(() => {
    refreshRunning();
    const id = setInterval(refreshRunning, 10000);
    return () => clearInterval(id);
  }, [refreshRunning]);

  const startModel = useCallback(async () => {
    setStarting(true);
    setError(null);
    try {
      if (window.electronAPI) {
        const result = await window.electronAPI.models.start();
        setRunning(true);
        return result;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start model');
      await refreshRunning();
      throw err;
    } finally {
      setStarting(false);
    }
  }, [refreshRunning]);

  const stopModel = useCallback(async () => {
    setStarting(true);
    try {
      if (window.electronAPI) {
        await window.electronAPI.models.stop();
      }
    } catch (err) {
      console.error('Failed to stop model:', err);
    } finally {
      setStarting(false);
      await refreshRunning();
    }
  }, [refreshRunning]);

  const isModelRunning = useCallback(async () => {
    try {
      if (window.electronAPI) {
        return await window.electronAPI.models.isRunning();
      }
      return false;
    } catch {
      return false;
    }
  }, []);

  const getServerUrl = useCallback(async () => {
    try {
      if (window.electronAPI) {
        return await window.electronAPI.models.getServerUrl();
      }
      return 'http://127.0.0.1:8765';
    } catch {
      return 'http://127.0.0.1:8765';
    }
  }, []);

  const getModelDir = useCallback(async () => {
    try {
      if (window.electronAPI) {
        return await window.electronAPI.models.getDir();
      }
      return '';
    } catch {
      return '';
    }
  }, []);

  const setModelDir = useCallback(async (path: string) => {
    try {
      if (window.electronAPI) {
        await window.electronAPI.models.setDir(path);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to set model directory');
      throw err;
    }
  }, []);

  return {
    availableModels,
    installedModels,
    currentModel,
    running,
    starting,
    isDownloading,
    downloadProgress,
    downloadingModel,
    error,
    downloadModel,
    deleteModel,
    selectModel,
    startModel,
    stopModel,
    isModelRunning,
    getServerUrl,
    getModelDir,
    setModelDir,
    refresh: () => {
      fetchAvailableModels();
      fetchInstalledModels();
      fetchCurrentModel();
    },
  };
}