import { app, BrowserWindow, ipcMain, dialog, shell, nativeTheme, Menu, Tray } from 'electron';
import { autoUpdater } from 'electron-updater';
import Store from 'electron-store';
import si from 'systeminformation';
import { join, resolve } from 'path';
import { existsSync, mkdirSync, writeFileSync, readFileSync, unlinkSync } from 'fs';
import { spawn, ChildProcess } from 'child_process';
import {
  getAvailableModels,
  getInstalledModels,
  getCurrentModel,
  setCurrentModel,
  downloadModel,
  deleteModel,
  startModelServer,
  stopModelServer,
  isModelRunning,
  getModelServerUrl,
  setModelServerPort,
  getModelDirPath,
  setModelDir,
  setupAutoUpdater,
  checkForUpdates,
  installUpdate,
  getAppVersion,
  getSystemStats,
  getLlamaServerStatus,
  killOrphanedModelServers,
} from './modelManager';
import { runFirstRunSetup, getInstallerStatus, resetFirstRun, installLlamaServer } from './installer';
import { listTools, runTool } from './tools';

interface AppConfig {
  modelPath: string;
  modelInstalled: boolean;
  autoStart: boolean;
  theme: 'dark' | 'light' | 'system';
  serverPort: number;
  gpuEnabled: boolean;
  modelDir: string;
  quantization: string;
  ctxSize: number;
  ctxSizeEffective: number;
  autoUpdate: boolean;
  minimizeToTray: boolean;
  closeToTray: boolean;
  startMinimized: boolean;
}

const store = new Store<AppConfig>({
  name: 'hercule-config',
  defaults: {
    modelPath: '',
    modelInstalled: false,
    autoStart: true,
    theme: 'dark',
    serverPort: 8765,
    gpuEnabled: true,
    modelDir: '',
    quantization: 'q4_k_m',
    ctxSize: 0,
    ctxSizeEffective: 0,
    autoUpdate: true,
    minimizeToTray: true,
    closeToTray: false,
    startMinimized: false,
  },
});

let mainWindow: BrowserWindow | null = null;
let tray: Tray | null = null;
let isQuitting = false;

const isDev = process.env.NODE_ENV === 'development';
const PRELOAD_PATH = join(__dirname, '../preload/index.js');
const RENDERER_URL = isDev ? 'http://localhost:5173' : `file://${join(__dirname, '../renderer/index.html')}`;

function createWindow(): void {
  const startMinimized = store.get('startMinimized');
  
  mainWindow = new BrowserWindow({
    width: 1600,
    height: 1000,
    minWidth: 1200,
    minHeight: 800,
    show: !startMinimized,
    titleBarStyle: 'hidden',
    trafficLightPosition: { x: 16, y: 16 },
    webPreferences: {
      preload: PRELOAD_PATH,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: !isDev,
    },
    icon: join(__dirname, '../../build/icon.png'),
    backgroundColor: '#0d1326',
  });

  mainWindow.loadURL(RENDERER_URL);

  mainWindow.once('ready-to-show', () => {
    if (!startMinimized) {
      mainWindow?.show();
    }
    if (isDev) {
      mainWindow?.webContents.openDevTools({ mode: 'detach' });
    }
  });

  mainWindow.on('close', (e: Electron.Event) => {
    if (!isQuitting) {
      const closeToTray = store.get('closeToTray');
      const minimizeToTray = store.get('minimizeToTray');
      
      if (process.platform === 'darwin') {
        e.preventDefault();
        mainWindow?.hide();
      } else if (closeToTray) {
        e.preventDefault();
        mainWindow?.hide();
        createTray();
      } else if (minimizeToTray) {
        e.preventDefault();
        mainWindow?.hide();
        createTray();
      }
    }
  });

  mainWindow.on('minimize', (e: Electron.Event) => {
    const minimizeToTray = store.get('minimizeToTray');
    if (minimizeToTray && process.platform !== 'darwin') {
      e.preventDefault();
      mainWindow?.hide();
      createTray();
    }
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  createTray();
}

function createTray(): void {
  if (tray) return;
  
  const iconPath = join(__dirname, '../../build/icon.png');
  tray = new Tray(iconPath);
  
  const contextMenu = Menu.buildFromTemplate([
    { label: 'Show HERCULE', click: () => mainWindow?.show() },
    { type: 'separator' },
    { label: 'Quit', click: () => { isQuitting = true; app.quit(); } },
  ]);
  
  tray.setToolTip('HERCULE - Your Local AI Assistant');
  tray.setContextMenu(contextMenu);
  
  tray.on('double-click', () => {
    mainWindow?.show();
  });
}

// Only one HERCULE may run: a second copy would double Electron's RAM
// and could spawn a second model server. Focus the existing window instead.
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.show();
      mainWindow.focus();
    }
  });
}

app.whenReady().then(async () => {
  // Reap inference servers orphaned by earlier runs (taskkill / crash leaves
  // them behind eating ~500MB + a CPU core each while the UI shows "stopped").
  try {
    await killOrphanedModelServers();
  } catch {
    // never block startup on cleanup
  }
  createWindow();
  setupAutoUpdater(mainWindow!);
  
  // Run first-run setup if needed
  if (mainWindow) {
    await runFirstRunSetup(mainWindow);
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin' || isQuitting) {
    stopModelServer();
    app.quit();
  }
});

app.on('before-quit', () => {
  isQuitting = true;
  stopModelServer();
  if (tray) {
    tray.destroy();
    tray = null;
  }
});

ipcMain.handle('config:get', () => store.store);
ipcMain.handle('config:set', (_, key: keyof AppConfig, value: any) => store.set(key, value));
ipcMain.handle('system:stats', getSystemStats);
ipcMain.handle('models:available', () => getAvailableModels());
ipcMain.handle('models:installed', () => getInstalledModels());
ipcMain.handle('models:current', () => getCurrentModel());
ipcMain.handle('models:set-current', (_, modelName: string) => setCurrentModel(modelName));
ipcMain.handle('model:download', async (_, modelName: string, quantization: string) => {
  return new Promise((resolve, reject) => {
    downloadModel(modelName, quantization, (progress, downloaded, total) => {
      mainWindow?.webContents.send('model:download-progress', { modelName, progress, downloaded, total });
    }).then(resolve).catch(reject);
  });
});
ipcMain.handle('model:delete', (_, modelName: string) => deleteModel(modelName));
ipcMain.handle('model:start', async () => {
  const currentModel = getCurrentModel();
  if (!currentModel) {
    throw new Error('No model selected');
  }
  const quantization = store.get('quantization');
  const ctxOverride = store.get('ctxSize') ?? 0;
  const info = await startModelServer(currentModel, quantization, ctxOverride);
  store.set('ctxSizeEffective', info.ctxSize);
  return info;
});
ipcMain.handle('model:stop', () => stopModelServer());
ipcMain.handle('model:running', () => isModelRunning());
ipcMain.handle('model:server-url', () => getModelServerUrl());
ipcMain.handle('model:dir', () => getModelDirPath());
ipcMain.handle('model:set-dir', (_, path: string) => setModelDir(path));
ipcMain.handle('app:quit', () => { isQuitting = true; app.quit(); });
ipcMain.handle('app:restart', () => { app.relaunch(); app.quit(); });
ipcMain.handle('app:version', () => getAppVersion());
ipcMain.handle('shell:openExternal', (_, url: string) => shell.openExternal(url));
ipcMain.handle('shell:showItemInFolder', (_, path: string) => shell.showItemInFolder(path));
ipcMain.handle('dialog:openFile', async (_, options) => {
  const result = await dialog.showOpenDialog(mainWindow!, options);
  return result.filePaths;
});
ipcMain.handle('dialog:openDirectory', async (_, options) => {
  const result = await dialog.showOpenDialog(mainWindow!, { ...options, properties: ['openDirectory'] });
  return result.filePaths;
});
ipcMain.handle('updater:check', () => checkForUpdates());
ipcMain.handle('updater:install', () => installUpdate());

// Installer IPC handlers
ipcMain.handle('installer:status', () => getInstallerStatus());
ipcMain.handle('installer:reset', () => resetFirstRun());
ipcMain.handle('installer:run-setup', async () => {
  if (mainWindow) {
    await runFirstRunSetup(mainWindow);
  }
});
ipcMain.handle('system:llama-status', () => getLlamaServerStatus());
ipcMain.handle('system:llama-install', async () => {
  if (mainWindow) {
    await installLlamaServer(mainWindow);
  }
  return getLlamaServerStatus();
});
ipcMain.handle('tools:list', () => listTools());
ipcMain.handle('tools:run', (_, name: string, toolArgs: Record<string, unknown>) => runTool(name, toolArgs ?? {}));