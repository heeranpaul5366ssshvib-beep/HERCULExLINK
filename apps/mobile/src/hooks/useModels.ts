import { useState, useEffect, useCallback } from 'react';

interface ModelInfo {
  name: string;
  version: string;
  url: string;
  size: number;
  sha256: string;
  description: string;
  quantizations: string[];
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
  const [isRunning, setIsRunning] = useState(false);

  const mockModels: ModelInfo[] = [
    {
      name: 'hercule-base-nano',
      version: '1.0.0',
      url: 'https://huggingface.co/HeeranPaul/hercule-base-nano/resolve/main/hercule-base-nano.gguf',
      size: 1500000000,
      sha256: 'placeholder',
      description: 'Ultra-lightweight model for quick responses (1.5GB)',
      quantizations: ['q4_k_m', 'q5_k_m', 'q8_0'],
    },
    {
      name: 'hercule-base-small',
      version: '1.0.0',
      url: 'https://huggingface.co/HeeranPaul/hercule-base-small/resolve/main/hercule-base-small.gguf',
      size: 3500000000,
      sha256: 'placeholder',
      description: 'Balanced model for general use (3.5GB)',
      quantizations: ['q4_k_m', 'q5_k_m', 'q8_0'],
    },
  ];

  useEffect(() => {
    setAvailableModels(mockModels);
    setInstalledModels([]);
    setCurrentModel(null);
    setIsRunning(false);
  }, []);

  const downloadModel = useCallback(async (modelName: string, quantization: string = 'q4_k_m') => {
    setError(null);
    setIsDownloading(true);
    setDownloadingModel(modelName);
    setDownloadProgress(0);

    try {
      for (let i = 0; i <= 100; i += 10) {
        await new Promise(r => setTimeout(r, 200));
        setDownloadProgress(i);
      }
      setInstalledModels(prev => [...prev, `${modelName}-${quantization}`]);
      setCurrentModel(`${modelName}-${quantization}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Download failed');
    } finally {
      setIsDownloading(false);
      setDownloadingModel(null);
    }
  }, []);

  const startModel = useCallback(async () => {
    if (!currentModel) return;
    setIsRunning(true);
    try {
      await new Promise(r => setTimeout(r, 1000));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start model');
      setIsRunning(false);
    }
  }, [currentModel]);

  const stopModel = useCallback(async () => {
    setIsRunning(false);
  }, []);

  const refresh = useCallback(() => {
    // Refresh logic
  }, []);

  return {
    availableModels,
    installedModels,
    currentModel,
    isDownloading,
    downloadProgress,
    downloadingModel,
    error,
    isModelRunning: isRunning,
    downloadModel,
    selectModel: async (name: string) => { setCurrentModel(name); },
    startModel,
    stopModel,
    refresh,
  };
}