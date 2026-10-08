import { contextBridge, ipcRenderer, IpcRendererEvent } from 'electron';

const ipc = {
  invoke: <T>(channel: string, ...args: unknown[]): Promise<T> => ipcRenderer.invoke(channel, ...args),
  on: (channel: string, callback: (event: IpcRendererEvent, ...args: unknown[]) => void) => {
    const listener = (_event: IpcRendererEvent, ...args: unknown[]) => callback(_event, ...args);
    ipcRenderer.on(channel, listener);
    return () => ipcRenderer.removeListener(channel, listener);
  },
  once: (channel: string, callback: (event: IpcRendererEvent, ...args: unknown[]) => void) => {
    ipcRenderer.once(channel, callback);
  },
  removeAllListeners: (channel: string) => ipcRenderer.removeAllListeners(channel),
};

contextBridge.exposeInMainWorld('electronAPI', {
  config: {
    get: () => ipc.invoke<Record<string, unknown>>('config:get'),
    set: (key: string, value: unknown) => ipc.invoke('config:set', key, value),
  },
  system: {
    getStats: () => ipc.invoke<{ cpu: number; ram: number; storage: number; gpu: number }>('system:stats'),
    onStatsUpdate: (callback: (stats: { cpu: number; ram: number; storage: number; gpu: number }) => void) =>
      ipc.on('system:stats-update', (_e, stats) => callback(stats)),
    getLlamaStatus: () => ipc.invoke<{ found: boolean; path: string; bundled: boolean }>('system:llama-status'),
    installLlama: () => ipc.invoke<{ found: boolean; path: string; bundled: boolean }>('system:llama-install'),
  },
  models: {
    getAvailable: () => ipc.invoke<Array<{
      name: string;
      version: string;
      url: string;
      size: number;
      sha256: string;
      description: string;
      quantizations: string[];
    }>>('models:available'),
    getInstalled: () => ipc.invoke<string[]>('models:installed'),
    getCurrent: () => ipc.invoke<string | null>('models:current'),
    setCurrent: (modelName: string) => ipc.invoke<void>('models:set-current', modelName),
    download: (modelName: string, quantization: string) => ipc.invoke<string>('model:download', modelName, quantization),
    onDownloadProgress: (callback: (progress: { modelName: string; progress: number; downloaded: number; total: number }) => void) =>
      ipc.on('model:download-progress', (_e, progress) => callback(progress)),
    delete: (modelName: string) => ipc.invoke<boolean>('model:delete', modelName),
    start: () => ipc.invoke<{ port: number; pid: number }>('model:start'),
    stop: () => ipc.invoke<void>('model:stop'),
    isRunning: () => ipc.invoke<boolean>('model:running'),
    getServerUrl: () => ipc.invoke<string>('model:server-url'),
    getDir: () => ipc.invoke<string>('model:dir'),
    setDir: (path: string) => ipc.invoke<void>('model:set-dir', path),
  },
  app: {
    quit: () => ipc.invoke<void>('app:quit'),
    restart: () => ipc.invoke<void>('app:restart'),
    getVersion: () => ipc.invoke<string>('app:version'),
  },
  shell: {
    openExternal: (url: string) => ipc.invoke<void>('shell:openExternal', url),
    showItemInFolder: (path: string) => ipc.invoke<void>('shell:showItemInFolder', path),
  },
  dialog: {
    openFile: (options?: Electron.OpenDialogOptions) =>
      ipc.invoke<string[]>('dialog:openFile', options),
    openDirectory: (options?: Electron.OpenDialogOptions) =>
      ipc.invoke<string[]>('dialog:openDirectory', options),
  },
  updater: {
    check: () => ipc.invoke<void>('updater:check'),
    install: () => ipc.invoke<void>('updater:install'),
    onStatus: (callback: (status: { status: string; version?: string; error?: string }) => void) =>
      ipc.on('updater:status', (_e, status) => callback(status)),
    onProgress: (callback: (progress: { percent: number; transferred: number; total: number }) => void) =>
      ipc.on('updater:progress', (_e, progress) => callback(progress)),
  },
  installer: {
    getStatus: () => ipc.invoke<{
      firstRun: boolean;
      modelInstalled: boolean;
      modelPath: string;
      shortcutsCreated: boolean;
      autoStartEnabled: boolean;
      telemetryOptIn: boolean | null;
    }>('installer:status'),
    reset: () => ipc.invoke<void>('installer:reset'),
    runSetup: () => ipc.invoke<void>('installer:run-setup'),
    onProgress: (callback: (progress: { stage: string; progress: number; message: string }) => void) =>
      ipc.on('installer:progress', (_e, progress) => callback(progress)),
  },
  tools: {
    list: () => ipc.invoke<Array<{ name: string; description: string; args: string[] }>>('tools:list'),
    run: (name: string, toolArgs: Record<string, unknown>) =>
      ipc.invoke<{ ok: boolean; output: string; error?: string }>('tools:run', name, toolArgs),
  },
});

contextBridge.exposeInMainWorld('nodeAPI', {
  platform: process.platform,
  versions: process.versions,
});

declare global {
  interface Window {
    electronAPI: {
      config: {
        get: () => Promise<Record<string, unknown>>;
        set: (key: string, value: unknown) => Promise<void>;
      };
      system: {
        getStats: () => Promise<{ cpu: number; ram: number; storage: number; gpu: number }>;
        onStatsUpdate: (callback: (stats: { cpu: number; ram: number; storage: number; gpu: number }) => void) => () => void;
        getLlamaStatus: () => Promise<{ found: boolean; path: string; bundled: boolean }>;
        installLlama: () => Promise<{ found: boolean; path: string; bundled: boolean }>;
      };
      models: {
        getAvailable: () => Promise<Array<{
          name: string;
          version: string;
          url: string;
          size: number;
          sha256: string;
          description: string;
          quantizations: string[];
        }>>;
        getInstalled: () => Promise<string[]>;
        getCurrent: () => Promise<string | null>;
        setCurrent: (modelName: string) => Promise<void>;
        download: (modelName: string, quantization: string) => Promise<string>;
        onDownloadProgress: (callback: (progress: { modelName: string; progress: number; downloaded: number; total: number }) => void) => () => void;
        delete: (modelName: string) => Promise<boolean>;
        start: () => Promise<{ port: number; pid: number }>;
        stop: () => Promise<void>;
        isRunning: () => Promise<boolean>;
        getServerUrl: () => Promise<string>;
        getDir: () => Promise<string>;
        setDir: (path: string) => Promise<void>;
      };
      app: {
        quit: () => Promise<void>;
        restart: () => Promise<void>;
        getVersion: () => Promise<string>;
      };
      shell: {
        openExternal: (url: string) => Promise<void>;
        showItemInFolder: (path: string) => Promise<void>;
      };
      dialog: {
        openFile: (options?: any) => Promise<string[]>;
        openDirectory: (options?: any) => Promise<string[]>;
      };
      updater: {
        check: () => Promise<void>;
        install: () => Promise<void>;
        onStatus: (callback: (status: any) => void) => () => void;
        onProgress: (callback: (progress: any) => void) => () => void;
      };
      installer: {
        getStatus: () => Promise<{
          firstRun: boolean;
          modelInstalled: boolean;
          modelPath: string;
          shortcutsCreated: boolean;
          autoStartEnabled: boolean;
          telemetryOptIn: boolean | null;
        }>;
        reset: () => Promise<void>;
        runSetup: () => Promise<void>;
        onProgress: (callback: (progress: { stage: string; progress: number; message: string }) => void) => () => void;
      };
      tools: {
        list: () => Promise<Array<{ name: string; description: string; args: string[] }>>;
        run: (name: string, toolArgs: Record<string, unknown>) => Promise<{ ok: boolean; output: string; error?: string }>;
      };
    };
    nodeAPI: { platform: string; versions: NodeJS.ProcessVersions };
  }
}