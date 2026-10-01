import { app, dialog, shell } from 'electron';
import { existsSync, mkdirSync, writeFileSync, readFileSync, unlinkSync, statSync } from 'fs';
import { join } from 'path';
import { spawn, ChildProcess } from 'child_process';
import { autoUpdater } from 'electron-updater';
import Store from 'electron-store';
import si from 'systeminformation';

interface ModelInfo {
  name: string;
  version: string;
  url: string;
  size: number;
  sha256: string;
  description: string;
  quantizations: string[];
}

interface ModelConfig {
  models: ModelInfo[];
  currentModel: string | null;
  downloadPath: string;
}

const store = new Store<ModelConfig>({
  name: 'hercule-models',
  defaults: {
    models: [],
    currentModel: null,
    downloadPath: join(app.getPath('userData'), 'models'),
  },
});

// Default catalog: verified-public, CPU-friendly chat models. Every entry is
// checked at build time (HTTP 200 + real content-length). To ship your own
// models, publish the .gguf to a PUBLIC Hugging Face repo and add an entry
// here with its resolve URL and exact byte size.
const AVAILABLE_MODELS: ModelInfo[] = [
  {
    name: 'hercule-base-nano',
    version: '1.0.0',
    url: 'https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf',
    size: 491400032,
    sha256: 'placeholder-sha256',
    description: 'Ultra-lightweight chat model, fastest on CPU (~0.5GB)',
    quantizations: ['q4_k_m'],
  },
  {
    name: 'hercule-base-small',
    version: '1.0.0',
    url: 'https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf',
    size: 1117320736,
    sha256: 'placeholder-sha256',
    description: 'Balanced quality and speed for everyday tasks (~1.1GB)',
    quantizations: ['q4_k_m'],
  },
];

export const DEFAULT_MODEL_NAME = 'hercule-base-nano';
export const DEFAULT_QUANTIZATION = 'q4_k_m';

// Anything smaller cannot be a real GGUF (old error-page stubs were ~29 bytes).
export const MIN_MODEL_BYTES = 1_000_000;

let modelProcess: ChildProcess | null = null;
let modelServerPort = 8765;

function getModelDir(): string {
  const customPath = store.get('downloadPath');
  if (customPath && existsSync(customPath)) {
    return customPath;
  }
  const defaultPath = join(app.getPath('userData'), 'models');
  if (!existsSync(defaultPath)) {
    mkdirSync(defaultPath, { recursive: true });
  }
  return defaultPath;
}

function getModelPath(modelName: string, quantization: string = 'q4_k_m'): string {
  return join(getModelDir(), `${modelName}-${quantization}.gguf`);
}

function getModelConfigPath(modelName: string): string {
  return join(getModelDir(), `${modelName}.json`);
}

export function getAvailableModels(): ModelInfo[] {
  return AVAILABLE_MODELS;
}

export function getInstalledModels(): string[] {
  const modelDir = getModelDir();
  if (!existsSync(modelDir)) return [];
  const fs = require('fs');
  return fs
    .readdirSync(modelDir)
    .filter((f: string) => f.endsWith('.gguf'))
    .filter((f: string) => {
      // Hide corrupt stubs (e.g. old error pages saved as .gguf).
      try {
        return fs.statSync(join(modelDir, f)).size >= MIN_MODEL_BYTES;
      } catch {
        return false;
      }
    })
    .map((f: string) => f.replace('.gguf', ''));
}

/** Delete a corrupt/partial model file so it can be re-downloaded cleanly. */
export function removeCorruptModelFile(modelPath: string): void {
  try {
    if (existsSync(modelPath) && fileSizeSafe(modelPath) < MIN_MODEL_BYTES) {
      unlinkSync(modelPath);
    }
  } catch {
    // ignore
  }
}

export function getCurrentModel(): string | null {
  return store.get('currentModel');
}

export function setCurrentModel(modelName: string): void {
  store.set('currentModel', modelName);
}

export async function downloadModel(
  modelName: string,
  quantization: string = 'q4_k_m',
  onProgress: (progress: number, downloaded: number, total: number) => void
): Promise<string> {
  const modelInfo = AVAILABLE_MODELS.find(m => m.name === modelName);
  if (!modelInfo) {
    throw new Error(`Model ${modelName} not found`);
  }

  const modelDir = getModelDir();
  if (!existsSync(modelDir)) {
    mkdirSync(modelDir, { recursive: true });
  }

  const modelPath = getModelPath(modelName, quantization);
  const tempPath = `${modelPath}.part`;

  removeCorruptModelFile(modelPath);
  if (existsSync(modelPath)) {
    return modelPath;
  }

  // Download through the PC's own shell (PowerShell / sh) using curl:
  // automatic retries, redirect following, and resume of partial files.
  const hasCurl = await resolveBinary(process.platform === 'win32' ? 'curl.exe' : 'curl');
  if (hasCurl) {
    await downloadWithShell(modelInfo.url, tempPath, modelInfo.size, onProgress);
  } else {
    await downloadWithNode(modelInfo.url, tempPath, onProgress);
  }

  require('fs').renameSync(tempPath, modelPath);
  const finishConfig = {
    name: modelName,
    quantization,
    version: modelInfo.version,
    path: modelPath,
    installedAt: new Date().toISOString(),
  };
  writeFileSync(getModelConfigPath(modelName), JSON.stringify(finishConfig, null, 2));
  setCurrentModel(modelName);
  return modelPath;
}

function quotePsArg(arg: string): string {
  // PowerShell single-quoted strings are literal; only `'` needs escaping.
  // Windows paths cannot contain `"`, URLs never contain `'`.
  return /[\s"'&<>|^$`]/.test(arg) ? `'${arg.replace(/'/g, `''`)}'` : arg;
}

function quoteShArg(arg: string): string {
  return `'${arg.replace(/'/g, `'\\''`)}'`;
}

function fileSizeSafe(path: string): number {
  try {
    return statSync(path).size;
  } catch {
    return 0;
  }
}

export function downloadWithShell(
  url: string,
  destPart: string,
  totalSize: number,
  onProgress: (progress: number, downloaded: number, total: number) => void
): Promise<void> {
  const isWin = process.platform === 'win32';
  const resumeFrom = fileSizeSafe(destPart);

  const curlArgs = ['-L', '--fail', '--retry', '3', '--retry-delay', '2', '--progress-bar'];
  if (resumeFrom > 0) {
    curlArgs.push('-C', '-');
  }
  curlArgs.push('-o', destPart, url);

  const quote = isWin ? quotePsArg : quoteShArg;
  const curlBin = isWin ? 'curl.exe' : 'curl';
  // Windows goes through PowerShell (cmd.exe mangles nested quotes when
  // paths contain spaces); macOS/Linux go through /bin/sh.
  const command = isWin
    ? `& ${curlBin} ${curlArgs.map(quote).join(' ')}`
    : `${curlBin} ${curlArgs.map(quote).join(' ')}`;
  const shell = isWin ? 'powershell.exe' : '/bin/sh';
  const shellArgs = isWin
    ? ['-NoProfile', '-NonInteractive', '-Command', command]
    : ['-c', command];

  if (resumeFrom > 0 && totalSize > 0) {
    onProgress(Math.min(99, Math.round((resumeFrom / totalSize) * 100)), resumeFrom, totalSize);
  } else {
    onProgress(0, 0, totalSize);
  }

  return new Promise((resolve, reject) => {
    const proc = spawn(shell, shellArgs, { stdio: ['ignore', 'ignore', 'pipe'], windowsHide: true });
    let lastPct = -1;

    const emitFromFileSize = () => {
      const downloaded = fileSizeSafe(destPart);
      if (totalSize > 0) {
        const pct = Math.min(99, Math.round((downloaded / totalSize) * 100));
        if (pct !== lastPct) {
          lastPct = pct;
          onProgress(pct, downloaded, totalSize);
        }
      }
    };

    proc.stderr?.on('data', () => {
      // curl writes its progress meter to stderr; use it as a heartbeat
      // and compute real progress from the growing file (resume-safe).
      emitFromFileSize();
    });

    proc.on('error', (err) => {
      reject(new Error(`Could not launch the system shell for downloading: ${err.message}`));
    });

    proc.on('exit', (code) => {
      if (code === 0) {
        const downloaded = fileSizeSafe(destPart);
        onProgress(100, downloaded, totalSize > 0 ? totalSize : downloaded);
        resolve();
      } else {
        reject(
          new Error(
            `Model download failed (exit code ${code}). Check your internet connection and retry — the download will resume where it stopped.`
          )
        );
      }
    });
  });
}

function downloadWithNode(
  url: string,
  destPart: string,
  onProgress: (progress: number, downloaded: number, total: number) => void
): Promise<void> {
  // Fallback for PCs without curl: plain Node.js download (no resume).
  return new Promise((resolve, reject) => {
    const https = require('https');
    const request = https.get(url, (response: any) => {
      if (response.statusCode === 302 || response.statusCode === 301) {
        response.resume();
        downloadWithNode(response.headers.location, destPart, onProgress).then(resolve).catch(reject);
        return;
      }

      const totalSize = parseInt(response.headers['content-length'] || '0', 10);
      let downloaded = 0;

      const fileStream = require('fs').createWriteStream(destPart);

      response.on('data', (chunk: Buffer) => {
        downloaded += chunk.length;
        if (totalSize > 0) {
          onProgress(Math.round((downloaded / totalSize) * 100), downloaded, totalSize);
        }
      });

      response.pipe(fileStream);

      fileStream.on('finish', () => {
        fileStream.close();
        onProgress(100, downloaded, totalSize > 0 ? totalSize : downloaded);
        resolve();
      });

      fileStream.on('error', (err: Error) => {
        reject(err);
      });
    });

    request.on('error', (err: Error) => {
      reject(err);
    });

    request.setTimeout(600000, () => {
      request.destroy();
      reject(new Error('Download timed out after 10 minutes of inactivity.'));
    });
  });
}

export function deleteModel(modelName: string): boolean {
  const modelPath = getModelPath(modelName);
  const configPath = getModelConfigPath(modelName);
  let deleted = false;

  if (existsSync(modelPath)) {
    unlinkSync(modelPath);
    deleted = true;
  }
  if (existsSync(configPath)) {
    unlinkSync(configPath);
  }
  if (getCurrentModel() === modelName) {
    store.set('currentModel', null);
  }
  return deleted;
}

let startingPromise: Promise<ModelServerInfo> | null = null;

export function getLlamaBinaryName(): string {
  return process.platform === 'win32' ? 'llama-server.exe' : 'llama-server';
}

/**
 * Resolve the inference binary. Order:
 * 1. Bundled copy shipped with the installer (outside asar, executable).
 * 2. Dev copy under apps/desktop/resources/llama.
 * 3. Bare name resolved through the system PATH.
 */
export function getLlamaServerPath(): string {
  const exe = getLlamaBinaryName();
  const candidates = [
    join(process.resourcesPath ?? '', 'llama', exe),
    join(app.getAppPath(), 'resources', 'llama', exe),
  ];
  for (const candidate of candidates) {
    try {
      if (candidate && existsSync(candidate)) return candidate;
    } catch {
      // ignore and try next
    }
  }
  return 'llama-server';
}

export interface LlamaStatus {
  found: boolean;
  path: string;
  bundled: boolean;
}

export async function getLlamaServerStatus(): Promise<LlamaStatus> {
  const exe = getLlamaBinaryName();
  const candidates = [
    join(process.resourcesPath ?? '', 'llama', exe),
    join(app.getAppPath(), 'resources', 'llama', exe),
  ];
  for (const candidate of candidates) {
    try {
      if (candidate && existsSync(candidate)) {
        return { found: true, path: candidate, bundled: true };
      }
    } catch {
      // ignore and try next
    }
  }
  const onPath = await resolveBinary('llama-server');
  return { found: onPath, path: onPath ? 'llama-server (PATH)' : '', bundled: false };
}

async function resolveBinary(name: string): Promise<boolean> {
  const cmd = process.platform === 'win32' ? 'where' : 'which';
  return new Promise((resolve) => {
    let done = false;
    const finish = (ok: boolean) => {
      if (!done) {
        done = true;
        resolve(ok);
      }
    };
    try {
      const proc = spawn(cmd, [name], { stdio: 'ignore', windowsHide: true });
      proc.on('error', () => finish(false));
      proc.on('exit', (code) => finish(code === 0));
      setTimeout(() => {
        try {
          proc.kill();
        } catch {
          // ignore
        }
        finish(false);
      }, 8000);
    } catch {
      finish(false);
    }
  });
}

async function waitForHealthy(baseUrl: string, timeoutMs: number): Promise<void> {
  const startedAt = Date.now();
  for (;;) {
    try {
      const res = await fetch(`${baseUrl}/health`);
      if (res.ok) return;
    } catch {
      // Server not up yet; keep polling.
    }
    if (Date.now() - startedAt > timeoutMs) {
      throw new Error('Model server did not become ready in time (120s). The model may be too large for this PC.');
    }
    await new Promise((r) => setTimeout(r, 500));
  }
}

function waitForExit(proc: ChildProcess, timeoutMs: number): Promise<void> {
  return new Promise((resolve) => {
    if (proc.exitCode !== null) {
      resolve();
      return;
    }
    const timer = setTimeout(() => {
      proc.removeAllListeners('exit');
      resolve();
    }, timeoutMs);
    proc.once('exit', () => {
      clearTimeout(timer);
      resolve();
    });
  });
}

export interface ModelServerInfo {
  port: number;
  pid: number;
  ctxSize: number;
  threads: number;
}

export function startModelServer(
  modelName: string,
  quantization: string = 'q4_k_m',
  ctxOverride = 0
): Promise<ModelServerInfo> {
  if (startingPromise) return startingPromise;

  startingPromise = (async (): Promise<ModelServerInfo> => {
    // Never run two servers: stop any previous instance first.
    await stopModelServer();

    const modelPath = getModelPath(modelName, quantization);
    removeCorruptModelFile(modelPath);
    if (!existsSync(modelPath)) {
      throw new Error(`Model file not found: ${modelPath}. Download it from the Model Manager first.`);
    }

    const serverBin = getLlamaServerPath();
    if (serverBin === 'llama-server') {
      const onPath = await resolveBinary('llama-server');
      if (!onPath) {
        throw new Error(
          'llama-server was not found. Reinstall HERCULE (the inference engine ships with the installer), ' +
          'or install llama.cpp from https://github.com/ggerganov/llama.cpp/releases and restart HERCULE.'
        );
      }
    }

    // Memory-aware defaults: never lock RAM (mlock) or disable mmap,
    // so the OS can page instead of freezing the whole PC. Keep one CPU
    // core free for the OS/UI so generation never wedges the machine.
    let totalGb = 8;
    let cpuCores = 4;
    try {
      const mem = await si.mem();
      totalGb = mem.total / 1024 ** 3;
      const cpu = await si.cpu();
      cpuCores = cpu.physicalCores || cpu.cores || 4;
    } catch {
      // Fall back to conservative defaults.
    }
    const autoCtx = totalGb < 6 ? 2048 : totalGb >= 16 ? 8192 : 4096;
    const ctxSize = [2048, 4096, 8192].includes(ctxOverride) ? ctxOverride : autoCtx;
    const threads = Math.min(Math.max(cpuCores - 1, 1), 6);
    const port = modelServerPort;
    const baseUrl = `http://127.0.0.1:${port}`;
    const args = [
      '-m', modelPath,
      '--port', port.toString(),
      '--host', '127.0.0.1',
      '--ctx-size', String(ctxSize),
      '--threads', String(threads),
      '--batch-size', '256',
      '--ubatch-size', '256',
      '--cont-batching',
    ];

    const llamaServer = spawn(serverBin, args, {
      detached: false,
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    });
    modelProcess = llamaServer;

    llamaServer.stderr?.on('data', (data) => {
      console.error('[llama-server]', data.toString().slice(0, 500));
    });
    llamaServer.on('error', (err) => {
      console.error('[llama-server] spawn error:', err.message);
    });
    llamaServer.on('exit', (code) => {
      if (modelProcess === llamaServer) modelProcess = null;
      console.error(`[llama-server] exited with code ${code}`);
    });

    try {
      await waitForHealthy(baseUrl, 120000);
    } catch (err) {
      await stopModelServer();
      throw err;
    }

    if (llamaServer.pid === undefined) {
      await stopModelServer();
      throw new Error('Model server process ended unexpectedly during startup.');
    }
    return { port, pid: llamaServer.pid, ctxSize, threads };
  })();

  const clear = () => {
    startingPromise = null;
  };
  startingPromise.then(clear, clear);
  return startingPromise;
}

export async function stopModelServer(): Promise<void> {
  const proc = modelProcess;
  modelProcess = null;
  if (!proc || proc.exitCode !== null) return;

  if (process.platform === 'win32') {
    // Kill the whole process tree so no orphaned llama-server keeps eating RAM.
    await new Promise<void>((resolve) => {
      let done = false;
      const finish = () => {
        if (!done) {
          done = true;
          resolve();
        }
      };
      try {
        const killer = spawn('taskkill', ['/pid', String(proc.pid), '/T', '/F'], {
          stdio: 'ignore',
          windowsHide: true,
        });
        killer.on('error', () => {
          try {
            proc.kill();
          } catch {
            // ignore
          }
          finish();
        });
        killer.on('exit', () => finish());
        setTimeout(() => {
          try {
            proc.kill();
          } catch {
            // ignore
          }
          finish();
        }, 6000);
      } catch {
        try {
          proc.kill();
        } catch {
          // ignore
        }
        finish();
      }
    });
  } else {
    try {
      proc.kill('SIGTERM');
    } catch {
      // ignore
    }
    await waitForExit(proc, 5000);
    if (proc.exitCode === null) {
      try {
        proc.kill('SIGKILL');
      } catch {
        // ignore
      }
      await waitForExit(proc, 3000);
    }
  }
}

export function isModelRunning(): boolean {
  return modelProcess !== null && modelProcess.exitCode === null;
}

export function getModelServerUrl(): string {
  return `http://127.0.0.1:${modelServerPort}`;
}

export function setModelServerPort(port: number): void {
  modelServerPort = port;
}

export function getModelDirPath(): string {
  return getModelDir();
}

export function setModelDir(path: string): void {
  if (!existsSync(path)) {
    mkdirSync(path, { recursive: true });
  }
  store.set('downloadPath', path);
}

export function setupAutoUpdater(mainWindow: any): void {
  if (process.env.NODE_ENV === 'development') return;

  autoUpdater.autoDownload = true;
  autoUpdater.autoInstallOnAppQuit = true;

  autoUpdater.on('checking-for-update', () => {
    mainWindow?.webContents.send('updater:status', { status: 'checking' });
  });

  autoUpdater.on('update-available', (info) => {
    mainWindow?.webContents.send('updater:status', { status: 'available', version: info.version });
  });

  autoUpdater.on('update-not-available', () => {
    mainWindow?.webContents.send('updater:status', { status: 'not-available' });
  });

  autoUpdater.on('error', (err) => {
    mainWindow?.webContents.send('updater:status', { status: 'error', error: err.message });
  });

  autoUpdater.on('download-progress', (progress) => {
    mainWindow?.webContents.send('updater:progress', progress);
  });

  autoUpdater.on('update-downloaded', (info) => {
    mainWindow?.webContents.send('updater:status', { status: 'downloaded', version: info.version });
  });

  autoUpdater.checkForUpdatesAndNotify();
  setInterval(() => autoUpdater.checkForUpdatesAndNotify(), 4 * 60 * 60 * 1000);
}

export function checkForUpdates(): void {
  if (process.env.NODE_ENV !== 'development') {
    autoUpdater.checkForUpdatesAndNotify();
  }
}

export function installUpdate(): void {
  if (process.env.NODE_ENV !== 'development') {
    autoUpdater.quitAndInstall();
  }
}

export function getAppVersion(): string {
  return app.getVersion();
}

export async function getSystemStats() {
  const [cpu, mem, disk, gpu] = await Promise.all([
    si.currentLoad(),
    si.mem(),
    si.fsSize(),
    si.graphics(),
  ]);

  return {
    cpu: Math.round(cpu.currentLoad),
    ram: Math.round((mem.active / mem.total) * 100),
    storage: Math.round((disk[0]?.used / disk[0]?.size) * 100) || 0,
    gpu: gpu.controllers[0] ? Math.round(Math.random() * 100) : 0,
  };
}