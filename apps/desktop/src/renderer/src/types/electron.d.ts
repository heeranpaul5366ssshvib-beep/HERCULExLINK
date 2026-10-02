export interface HerculeModelInfo {
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

export interface HerculeSystemStats {
  cpu: number;
  ram: number;
  storage: number;
  gpu: number;
}

export interface HerculeDownloadProgress {
  modelName: string;
  progress: number;
  downloaded: number;
  total: number;
}

export interface HerculeUpdaterStatus {
  status: string;
  version?: string;
  error?: string;
}

export interface HerculeUpdaterProgress {
  percent: number;
  transferred: number;
  total: number;
}

export interface HerculeInstallerStatus {
  firstRun: boolean;
  modelInstalled: boolean;
  modelPath: string;
  shortcutsCreated: boolean;
  autoStartEnabled: boolean;
  telemetryOptIn: boolean | null;
}

export interface HerculeInstallerProgress {
  stage: string;
  progress: number;
  message: string;
}

export interface HerculeLlamaStatus {
  found: boolean;
  path: string;
  bundled: boolean;
}

export interface HerculeElectronAPI {
  config: {
    get: () => Promise<Record<string, unknown>>;
    set: (key: string, value: unknown) => Promise<void>;
  };
  system: {
    getStats: () => Promise<HerculeSystemStats>;
    onStatsUpdate: (callback: (stats: HerculeSystemStats) => void) => () => void;
    getLlamaStatus: () => Promise<HerculeLlamaStatus>;
    installLlama: () => Promise<HerculeLlamaStatus>;
  };
  models: {
    getAvailable: () => Promise<HerculeModelInfo[]>;
    getInstalled: () => Promise<string[]>;
    getCurrent: () => Promise<string | null>;
    setCurrent: (modelName: string) => Promise<void>;
    download: (modelName: string, quantization: string) => Promise<string>;
    onDownloadProgress: (callback: (progress: HerculeDownloadProgress) => void) => () => void;
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
    openFile: (options?: unknown) => Promise<string[]>;
    openDirectory: (options?: unknown) => Promise<string[]>;
  };
  updater: {
    check: () => Promise<void>;
    install: () => Promise<void>;
    onStatus: (callback: (status: HerculeUpdaterStatus) => void) => () => void;
    onProgress: (callback: (progress: HerculeUpdaterProgress) => void) => () => void;
  };
  installer: {
    getStatus: () => Promise<HerculeInstallerStatus>;
    reset: () => Promise<void>;
    runSetup: () => Promise<void>;
    onProgress: (callback: (progress: HerculeInstallerProgress) => void) => () => void;
  };
}

declare global {
  interface Window {
    electronAPI: HerculeElectronAPI;
    nodeAPI: { platform: string; versions: NodeJS.ProcessVersions };
  }
}

export {};
