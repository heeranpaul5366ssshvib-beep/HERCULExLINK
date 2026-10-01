import { app, dialog, shell, BrowserWindow } from 'electron';
import { join } from 'path';
import { existsSync, mkdirSync } from 'fs';
import { spawn } from 'child_process';
import Store from 'electron-store';

interface InstallerConfig {
  firstRun: boolean;
  modelInstalled: boolean;
  modelPath: string;
  shortcutsCreated: boolean;
  autoStartEnabled: boolean;
  telemetryOptIn: boolean | null;
}

const installerStore = new Store<InstallerConfig>({
  name: 'hercule-installer',
  defaults: {
    firstRun: true,
    modelInstalled: false,
    modelPath: '',
    shortcutsCreated: false,
    autoStartEnabled: false,
    telemetryOptIn: null,
  },
});

const DEFAULT_MODEL = 'hercule-base-nano';
const DEFAULT_QUANTIZATION = 'q4_k_m';
const MODEL_URL =
  'https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf';
const MODEL_SIZE = 491400032;

export async function runFirstRunSetup(mainWindow: BrowserWindow): Promise<void> {
  if (!installerStore.get('firstRun')) {
    return;
  }

  try {
    // Show welcome dialog
    const welcomeResult = await dialog.showMessageBox(mainWindow, {
      type: 'info',
      title: 'Welcome to HERCULE',
      message: 'Welcome to HERCULE - Your Local AI Assistant!',
      detail: 'This appears to be your first run. We\'ll help you set up HERCULE with a local AI model.\n\nThis process will:\n• Download a lightweight AI model (~1.5 GB)\n• Configure system settings\n• Create shortcuts\n• Enable auto-start (optional)',
      buttons: ['Get Started', 'Skip for Now'],
      defaultId: 0,
      cancelId: 1,
      checkboxLabel: 'Send anonymous usage statistics to improve HERCULE',
      checkboxChecked: false,
    });

    if (welcomeResult.response === 1) {
      // User clicked "Skip for Now"
      installerStore.set('firstRun', false);
      return;
    }

    // Handle telemetry opt-in
    installerStore.set('telemetryOptIn', welcomeResult.checkboxChecked);

    // Check for llama-server
    const hasLlamaServer = await checkLlamaServer();
    if (!hasLlamaServer) {
      await installLlamaServer(mainWindow);
    }

    // Download model
    await downloadModelWithProgress(mainWindow);

    // Create shortcuts
    await createShortcuts(mainWindow);

    // Configure auto-start
    await configureAutoStart(mainWindow);

    // Mark first run as complete
    installerStore.set('firstRun', false);
    installerStore.set('modelInstalled', true);

    // Show completion dialog
    await dialog.showMessageBox(mainWindow, {
      type: 'info',
      title: 'Setup Complete!',
      message: 'HERCULE is ready to use!',
      detail: 'Your local AI assistant has been set up successfully. You can now start chatting with HERCULE.\n\nThe model will start automatically when you open the chat.',
      buttons: ['Start Chatting'],
    });

  } catch (error) {
    console.error('First run setup failed:', error);
    await dialog.showMessageBox(mainWindow, {
      type: 'error',
      title: 'Setup Incomplete',
      message: 'Some setup steps could not be completed.',
      detail: `Error: ${error instanceof Error ? error.message : 'Unknown error'}\n\nYou can retry setup from Settings > General > Run Setup Wizard.`,
      buttons: ['OK'],
    });
  }
}

async function checkLlamaServer(): Promise<boolean> {
  const { getLlamaServerStatus } = await import('./modelManager');
  const status = await getLlamaServerStatus();
  if (status.found) return true;
  return new Promise((resolve) => {
    const proc = spawn('llama-server', ['--version'], {
      stdio: 'ignore',
      windowsHide: true
    });
    
    proc.on('error', () => resolve(false));
    proc.on('exit', (code) => resolve(code === 0));
    
    // Timeout after 5 seconds
    setTimeout(() => {
      proc.kill();
      resolve(false);
    }, 5000);
  });
}

export async function installLlamaServer(mainWindow: BrowserWindow): Promise<void> {
  const result = await dialog.showMessageBox(mainWindow, {
    type: 'question',
    title: 'Install llama.cpp',
    message: 'HERCULE requires llama.cpp to run local AI models.',
    detail: 'Would you like to install llama.cpp now? This will download and install the inference engine (~50 MB).',
    buttons: ['Install Automatically', 'I\'ll Install Manually'],
    defaultId: 0,
    cancelId: 1,
  });

  if (result.response === 1) {
    // User will install manually
    await shell.openExternal('https://github.com/ggerganov/llama.cpp/releases');
    throw new Error('llama.cpp not installed. Please install it manually and restart HERCULE.');
  }

  // Auto-install based on platform
  const platform = process.platform;
  
  try {
    if (platform === 'win32') {
      await installLlamaServerWindows(mainWindow);
    } else if (platform === 'darwin') {
      await installLlamaServerMacOS(mainWindow);
    } else if (platform === 'linux') {
      await installLlamaServerLinux(mainWindow);
    }
  } catch (error) {
    throw new Error(`Failed to install llama.cpp: ${error instanceof Error ? error.message : 'Unknown error'}`);
  }
}

async function installLlamaServerWindows(mainWindow: BrowserWindow): Promise<void> {
  // Download and run winget or chocolatey
  const hasWinget = await checkCommand('winget');
  const hasChoco = await checkCommand('choco');
  
  if (hasWinget) {
    await runWithProgress(mainWindow, 'Installing llama.cpp via winget...', async () => {
      return new Promise<void>((resolve, reject) => {
        const proc = spawn('winget', ['install', '--id', 'ggerganov.llama.cpp', '-e', '--accept-source-agreements', '--accept-package-agreements'], {
          stdio: 'pipe',
          windowsHide: true,
        });
        
        proc.on('exit', (code) => code === 0 ? resolve() : reject(new Error(`winget exited with code ${code}`)));
        proc.on('error', reject);
      });
    });
  } else if (hasChoco) {
    await runWithProgress(mainWindow, 'Installing llama.cpp via Chocolatey...', async () => {
      return new Promise<void>((resolve, reject) => {
        const proc = spawn('choco', ['install', 'llama.cpp', '-y'], {
          stdio: 'pipe',
          windowsHide: true,
        });
        
        proc.on('exit', (code) => code === 0 ? resolve() : reject(new Error(`choco exited with code ${code}`)));
        proc.on('error', reject);
      });
    });
  } else {
    // Download prebuilt binary
    await downloadLlamaCppBinary(mainWindow);
  }
}

async function installLlamaServerMacOS(mainWindow: BrowserWindow): Promise<void> {
  const hasBrew = await checkCommand('brew');
  
  if (hasBrew) {
    await runWithProgress(mainWindow, 'Installing llama.cpp via Homebrew...', async () => {
      return new Promise<void>((resolve, reject) => {
        const proc = spawn('brew', ['install', 'llama.cpp'], {
          stdio: 'pipe',
        });
        
        proc.on('exit', (code) => code === 0 ? resolve() : reject(new Error(`brew exited with code ${code}`)));
        proc.on('error', reject);
      });
    });
  } else {
    await downloadLlamaCppBinary(mainWindow);
  }
}

async function installLlamaServerLinux(mainWindow: BrowserWindow): Promise<void> {
  // Try package managers
  const managers = [
    { cmd: 'apt', args: ['install', '-y', 'llama.cpp'] },
    { cmd: 'dnf', args: ['install', '-y', 'llama.cpp'] },
    { cmd: 'pacman', args: ['-S', '--noconfirm', 'llama.cpp'] },
    { cmd: 'zypper', args: ['install', '-y', 'llama.cpp'] },
  ];
  
  for (const mgr of managers) {
    if (await checkCommand(mgr.cmd)) {
      await runWithProgress(mainWindow, `Installing llama.cpp via ${mgr.cmd}...`, async () => {
        return new Promise<void>((resolve, reject) => {
          const proc = spawn('sudo', [mgr.cmd, ...mgr.args], {
            stdio: 'pipe',
          });
          
          proc.on('exit', (code) => code === 0 ? resolve() : reject(new Error(`${mgr.cmd} exited with code ${code}`)));
          proc.on('error', reject);
        });
      });
      return;
    }
  }
  
  // Fallback to binary download
  await downloadLlamaCppBinary(mainWindow);
}

async function checkCommand(cmd: string): Promise<boolean> {
  return new Promise((resolve) => {
    const proc = spawn('which', [cmd], { stdio: 'ignore' });
    proc.on('exit', (code) => resolve(code === 0));
    proc.on('error', () => resolve(false));
  });
}

async function downloadLlamaCppBinary(mainWindow: BrowserWindow): Promise<void> {
  await dialog.showMessageBox(mainWindow, {
    type: 'info',
    title: 'Manual Installation Required',
    message: 'Could not install llama.cpp automatically.',
    detail: 'Please download llama.cpp from https://github.com/ggerganov/llama.cpp/releases and add it to your PATH.\n\nAfter installation, restart HERCULE.',
    buttons: ['Open Download Page', 'OK'],
  });
  
  await shell.openExternal('https://github.com/ggerganov/llama.cpp/releases');
  throw new Error('Please install llama.cpp manually');
}

async function downloadModelWithProgress(mainWindow: BrowserWindow): Promise<string> {
  const modelDir = join(app.getPath('userData'), 'models');
  if (!existsSync(modelDir)) {
    mkdirSync(modelDir, { recursive: true });
  }
  
  const modelPath = join(modelDir, `${DEFAULT_MODEL}-${DEFAULT_QUANTIZATION}.gguf`);
  const tempPath = `${modelPath}.part`;

  // Reuse the same PowerShell/curl downloader as the Model Manager so
  // first-run downloads get retries, redirects and resume support.
  const { downloadWithShell, removeCorruptModelFile, setCurrentModel } = await import('./modelManager');
  removeCorruptModelFile(modelPath);
  if (existsSync(modelPath)) {
    installerStore.set('modelPath', modelPath);
    setCurrentModel(DEFAULT_MODEL);
    return modelPath;
  }

  mainWindow.webContents.send('installer:progress', {
    stage: 'downloading-model',
    progress: 0,
    message: 'Downloading AI model (PowerShell + curl, resumable)…',
  });

  await downloadWithShell(MODEL_URL, tempPath, MODEL_SIZE, (progress) => {
    mainWindow.webContents.send('installer:progress', {
      stage: 'downloading-model',
      progress,
      message: `Downloading AI model... ${progress}%`,
    });
  });

  require('fs').renameSync(tempPath, modelPath);
  installerStore.set('modelPath', modelPath);
  mainWindow.webContents.send('installer:progress', {
    stage: 'downloading-model',
    progress: 100,
    message: 'Model downloaded successfully!',
  });

  // Register it as the current model so chat works immediately.
  setCurrentModel(DEFAULT_MODEL);
  return modelPath;
}

async function createShortcuts(mainWindow: BrowserWindow): Promise<void> {
  if (installerStore.get('shortcutsCreated')) {
    return;
  }
  
  const platform = process.platform;
  
  try {
    if (platform === 'win32') {
      // Windows shortcuts are created by NSIS installer
      installerStore.set('shortcutsCreated', true);
    } else if (platform === 'darwin') {
      // macOS aliases created by DMG
      installerStore.set('shortcutsCreated', true);
    } else if (platform === 'linux') {
      // Create .desktop file
      const desktopEntry = `[Desktop Entry]
Name=HERCULE
Comment=Your Local AI Assistant
Exec=${app.getPath('exe')}
Icon=hercule
Terminal=false
Type=Application
Categories=Development;Utility;
StartupNotify=true
`;
      
      const applicationsDir = join(process.env.HOME || '', '.local', 'share', 'applications');
      if (!existsSync(applicationsDir)) {
        mkdirSync(applicationsDir, { recursive: true });
      }
      
      const desktopPath = join(applicationsDir, 'hercule.desktop');
      require('fs').writeFileSync(desktopPath, desktopEntry);
      installerStore.set('shortcutsCreated', true);
    }
  } catch (error) {
    console.warn('Failed to create shortcuts:', error);
  }
}

async function configureAutoStart(mainWindow: BrowserWindow): Promise<void> {
  const result = await dialog.showMessageBox(mainWindow, {
    type: 'question',
    title: 'Auto-start HERCULE',
    message: 'Would you like HERCULE to start automatically when you log in?',
    detail: 'This will launch HERCULE in the background so it\'s ready when you need it.',
    buttons: ['Yes, Auto-start', 'No, Start Manually'],
    defaultId: 0,
    cancelId: 1,
  });
  
  if (result.response === 0) {
    app.setLoginItemSettings({
      openAtLogin: true,
      openAsHidden: true,
    });
    installerStore.set('autoStartEnabled', true);
  }
}

async function runWithProgress(
  mainWindow: BrowserWindow,
  message: string,
  fn: () => Promise<void>
): Promise<void> {
  mainWindow.webContents.send('installer:progress', { 
    stage: 'installing-dependencies', 
    progress: 0, 
    message 
  });
  
  try {
    await fn();
    mainWindow.webContents.send('installer:progress', { 
      stage: 'installing-dependencies', 
      progress: 100, 
      message: 'Done!' 
    });
  } catch (error) {
    mainWindow.webContents.send('installer:progress', { 
      stage: 'installing-dependencies', 
      progress: 0, 
      message: `Failed: ${error instanceof Error ? error.message : 'Unknown error'}` 
    });
    throw error;
  }
}

export function getInstallerStatus() {
  return {
    firstRun: installerStore.get('firstRun'),
    modelInstalled: installerStore.get('modelInstalled'),
    modelPath: installerStore.get('modelPath'),
    shortcutsCreated: installerStore.get('shortcutsCreated'),
    autoStartEnabled: installerStore.get('autoStartEnabled'),
    telemetryOptIn: installerStore.get('telemetryOptIn'),
  };
}

export function resetFirstRun() {
  installerStore.set('firstRun', true);
}