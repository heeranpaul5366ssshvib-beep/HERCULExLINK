// Downloads a prebuilt llama.cpp server binary for the host platform and
// stages it under resources/llama/ so it ships inside the installer.
// Idempotent: skips when the binary is already present (use --force to refetch).
// No npm dependencies: uses the OS curl / PowerShell / tar.
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, rmSync, readdirSync, copyFileSync, writeFileSync, chmodSync, readFileSync } from 'node:fs';
import { join, dirname, basename } from 'node:path';
import { fileURLToPath } from 'node:url';
import os from 'node:os';

const here = dirname(fileURLToPath(import.meta.url));
const appDir = join(here, '..');
const outDir = join(appDir, 'resources', 'llama');
const tmpDir = join(os.tmpdir(), 'hercule-llama-fetch');
const force = process.argv.includes('--force');

const platform = process.platform;
const arch = process.arch === 'arm64' ? 'arm64' : 'x64';
const exeName = platform === 'win32' ? 'llama-server.exe' : 'llama-server';

function assetPattern() {
  if (platform === 'win32') {
    return arch === 'arm64' ? /llama-b\d+-bin-win-cpu-arm64\.zip$/ : /llama-b\d+-bin-win-cpu-x64\.zip$/;
  }
  if (platform === 'darwin') {
    return arch === 'arm64' ? /llama-b\d+-bin-macos-arm64\.tar\.gz$/ : /llama-b\d+-bin-macos-x64\.tar\.gz$/;
  }
  return arch === 'arm64' ? /llama-b\d+-bin-ubuntu-arm64\.tar\.gz$/ : /llama-b\d+-bin-ubuntu-x64\.tar\.gz$/;
}

function runCurl(args, outFile = null) {
  const finalArgs = outFile ? [...args, '-o', outFile] : args;
  const res = spawnSync('curl', finalArgs, {
    stdio: ['ignore', 'inherit', 'pipe'],
    encoding: 'utf8',
    windowsHide: true,
  });
  if (res.error) throw new Error(`curl failed to start: ${res.error.message}`);
  if (res.status !== 0) {
    const detail = String(res.stderr || '').slice(-300) || `exit ${res.status}`;
    throw new Error(`curl failed: ${detail}`);
  }
}

function githubApi(path, outFile) {
  const args = ['-sL', '--fail', '--retry', '3', `https://api.github.com${path}`];
  if (process.env.GITHUB_TOKEN) args.splice(1, 0, '-H', `Authorization: Bearer ${process.env.GITHUB_TOKEN}`);
  runCurl(args, outFile);
  return JSON.parse(readFileSync(outFile, 'utf8'));
}

function main() {
  if (!force && existsSync(join(outDir, exeName))) {
    console.log(`[fetch-llama] ${exeName} already bundled, skipping (use --force to refetch).`);
    return;
  }

  const pattern = assetPattern();
  console.log(`[fetch-llama] looking for llama.cpp build matching ${pattern} ...`);
  rmSync(tmpDir, { recursive: true, force: true });
  mkdirSync(tmpDir, { recursive: true });
  const releases = githubApi('/repos/ggerganov/llama.cpp/releases?per_page=30', join(tmpDir, 'releases.json'));
  let found = null;
  for (const rel of releases) {
    const asset = (rel.assets || []).find((a) => pattern.test(a.name));
    if (asset) {
      found = { tag: rel.tag_name, asset };
      break;
    }
  }
  if (!found) throw new Error('No matching llama.cpp binary found in recent releases.');

  console.log(`[fetch-llama] found ${found.asset.name} (${found.tag}, ${(found.asset.size / 1048576).toFixed(1)} MB)`);
  const archivePath = join(tmpDir, found.asset.name);
  runCurl(['-L', '--fail', '--retry', '3', '--retry-delay', '2', found.asset.browser_download_url], archivePath);

  const extractDir = join(tmpDir, 'extracted');
  mkdirSync(extractDir, { recursive: true });
  if (platform === 'win32') {
    const ps = spawnSync(
      'powershell.exe',
      ['-NoProfile', '-NonInteractive', '-Command', `Expand-Archive -Force -Path '${archivePath}' -DestinationPath '${extractDir}'`],
      { stdio: 'inherit', windowsHide: true }
    );
    if (ps.status !== 0) throw new Error('Expand-Archive failed.');
  } else {
    const tar = spawnSync('tar', ['-xzf', archivePath, '-C', extractDir], { stdio: 'inherit' });
    if (tar.status !== 0) throw new Error('tar extraction failed.');
  }

  const keep =
    platform === 'win32'
      ? (f) => f === 'llama-server.exe' || f.toLowerCase().endsWith('.dll')
      : (f) => f === 'llama-server' || /\.so(\.|$)/.test(f) || f.endsWith('.dylib') || f.endsWith('.metal');

  const staged = [];
  const walk = (dir) => {
    for (const entry of readdirSync(dir, { withFileTypes: true })) {
      const full = join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(full);
      } else if (keep(entry.name)) {
        staged.push(full);
      }
    }
  };
  walk(extractDir);

  if (!staged.some((f) => basename(f) === exeName)) {
    throw new Error(`Archive did not contain ${exeName}.`);
  }

  rmSync(outDir, { recursive: true, force: true });
  mkdirSync(outDir, { recursive: true });
  for (const src of staged) {
    copyFileSync(src, join(outDir, basename(src)));
  }
  if (platform !== 'win32') {
    try {
      chmodSync(join(outDir, exeName), 0o755);
    } catch {
      // ignore
    }
  }
  writeFileSync(
    join(outDir, 'MANIFEST.json'),
    JSON.stringify({ tag: found.tag, asset: found.asset.name, platform, arch, fetchedAt: new Date().toISOString() }, null, 2)
  );
  rmSync(tmpDir, { recursive: true, force: true });

  console.log(`[fetch-llama] staged ${staged.length} file(s) into resources/llama/`);
}

try {
  main();
} catch (err) {
  console.error(`[fetch-llama] FAILED: ${err instanceof Error ? err.message : err}`);
  process.exit(1);
}
