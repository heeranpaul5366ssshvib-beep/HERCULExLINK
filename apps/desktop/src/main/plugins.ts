// v2.5: local plugin marketplace. Built-ins ship with the app; community
// plugins install from a folder containing manifest.json. Install consent IS
// the permission grant: permissions are shown before install, stored, and
// enforced — plugins only ever reach the read-only tool bridge.
import { app } from 'electron';
import { existsSync, promises as fs } from 'fs';
import { join, resolve, sep } from 'path';
import Store from 'electron-store';

export interface PluginManifest {
  id: string;
  name: string;
  version: string;
  description: string;
  category: string;
  permissions: string[];
}

/** Permissions a community plugin may request. Anything else is rejected. */
export const ALLOWED_PERMISSIONS = new Set([
  'read-files',
  'web-fetch',
  'calculator',
  'notifications',
  'clipboard',
]);

const BUILT_IN_IDS = new Set([
  'github', 'web', 'drive', 'vscode', 'terminal', 'files', 'calendar', 'email',
]);

export interface InstalledPlugin extends PluginManifest {
  source: 'built-in' | 'community';
  enabled: boolean;
  path?: string;
}

interface PluginStoreShape {
  enabled: Record<string, boolean>;
  grants: Record<string, string[]>;
}

const store = new Store<PluginStoreShape>({
  name: 'hercule-plugins',
  defaults: { enabled: { github: true, web: true, vscode: true }, grants: {} },
});

const BUILT_IN_META: Array<Omit<PluginManifest, 'permissions'> & { permissions: string[] }> = [
  { id: 'github', name: 'GitHub', version: '2.1.0', description: 'Repositories & Issues', category: 'Development', permissions: ['web-fetch', 'clipboard'] },
  { id: 'web', name: 'Web Search', version: '1.4.0', description: 'Real-time search', category: 'Research', permissions: ['web-fetch'] },
  { id: 'drive', name: 'Google Drive', version: '1.0.0', description: 'File access', category: 'Files', permissions: ['read-files'] },
  { id: 'vscode', name: 'VS Code', version: '1.2.0', description: 'Editor integration', category: 'Development', permissions: ['read-files', 'clipboard'] },
  { id: 'terminal', name: 'Terminal', version: '1.0.0', description: 'Run approved shell commands locally.', category: 'Development', permissions: [] },
  { id: 'files', name: 'Local Files', version: '1.0.0', description: 'Search and read files in your workspace.', category: 'Files', permissions: ['read-files'] },
  { id: 'calendar', name: 'Calendar', version: '1.0.0', description: 'See upcoming events and plan around them.', category: 'Productivity', permissions: ['notifications'] },
  { id: 'email', name: 'Email', version: '1.0.0', description: 'Summarize threads and draft replies.', category: 'Productivity', permissions: ['notifications', 'clipboard'] },
];

function pluginsDir(): string {
  const dir = join(app.getPath('userData'), 'plugins');
  if (!existsSync(dir)) {
    const { mkdirSync } = require('fs');
    mkdirSync(dir, { recursive: true });
  }
  return dir;
}

function validateManifest(raw: unknown): { ok: true; manifest: PluginManifest } | { ok: false; error: string } {
  if (typeof raw !== 'object' || raw === null) return { ok: false, error: 'manifest.json must contain a JSON object' };
  const m = raw as Record<string, unknown>;
  if (typeof m.id !== 'string' || !/^[a-z0-9-]{2,32}$/.test(m.id)) {
    return { ok: false, error: 'id must be 2–32 chars: lowercase letters, digits, dashes' };
  }
  if (BUILT_IN_IDS.has(m.id)) return { ok: false, error: `id '${m.id}' is reserved by a built-in plugin` };
  for (const field of ['name', 'version', 'description', 'category'] as const) {
    if (typeof m[field] !== 'string' || (m[field] as string).trim().length === 0) {
      return { ok: false, error: `missing or empty '${field}'` };
    }
    if ((m[field] as string).length > 200) return { ok: false, error: `'${field}' too long (max 200)` };
  }
  if (!Array.isArray(m.permissions)) return { ok: false, error: 'permissions must be an array' };
  for (const p of m.permissions as unknown[]) {
    if (typeof p !== 'string' || !ALLOWED_PERMISSIONS.has(p)) {
      return { ok: false, error: `permission '${String(p)}' is not allowed (allowed: ${[...ALLOWED_PERMISSIONS].join(', ')})` };
    }
  }
  return {
    ok: true,
    manifest: {
      id: m.id as string,
      name: (m.name as string).trim(),
      version: (m.version as string).trim(),
      description: (m.description as string).trim(),
      category: (m.category as string).trim(),
      permissions: [...new Set(m.permissions as string[])],
    },
  };
}

async function readCommunityPlugins(): Promise<PluginManifest[]> {
  const dir = pluginsDir();
  let entries;
  try {
    entries = await fs.readdir(dir, { withFileTypes: true });
  } catch {
    return [];
  }
  const out: PluginManifest[] = [];
  for (const e of entries) {
    if (!e.isDirectory()) continue;
    try {
      const raw = JSON.parse(await fs.readFile(join(dir, e.name, 'manifest.json'), 'utf8'));
      const v = validateManifest(raw);
      if (v.ok && v.manifest.id === e.name) out.push(v.manifest);
    } catch {
      // broken plugin folder — skipped, never loaded
    }
  }
  return out;
}

export async function listPlugins(): Promise<InstalledPlugin[]> {
  const enabled = store.get('enabled');
  const community = await readCommunityPlugins();
  const builtIns: InstalledPlugin[] = BUILT_IN_META.map((b) => ({
    ...b,
    source: 'built-in' as const,
    enabled: enabled[b.id] ?? false,
  }));
  const mine: InstalledPlugin[] = community.map((m) => ({
    ...m,
    source: 'community' as const,
    enabled: enabled[m.id] ?? true,
    path: join(pluginsDir(), m.id),
  }));
  return [...builtIns, ...mine];
}

/** Preview a manifest before install so the UI can show the permission grant. */
export async function previewPlugin(folder: string): Promise<PluginManifest> {
  const abs = resolve(folder);
  const base = resolve(pluginsDir());
  if (abs === base || abs.startsWith(base + sep)) {
    throw new Error('Pick the plugin source folder, not the install directory.');
  }
  let raw: unknown;
  try {
    raw = JSON.parse(await fs.readFile(join(abs, 'manifest.json'), 'utf8'));
  } catch {
    throw new Error('No readable manifest.json in that folder.');
  }
  const v = validateManifest(raw);
  if (!v.ok) throw new Error(`Invalid plugin: ${v.error}`);
  return v.manifest;
}

export async function installPlugin(folder: string): Promise<InstalledPlugin> {
  const manifest = await previewPlugin(folder);
  const dest = join(pluginsDir(), manifest.id);
  await fs.rm(dest, { recursive: true, force: true });
  await fs.mkdir(dest, { recursive: true });
  // Copy files (manifest + assets), skipping caches and oversized files.
  const entries = await fs.readdir(resolve(folder), { withFileTypes: true });
  for (const e of entries) {
    if (!e.isFile() || e.name.startsWith('.')) continue;
    const src = join(resolve(folder), e.name);
    const st = await fs.stat(src);
    if (st.size > 5 * 1024 * 1024) continue;
    await fs.copyFile(src, join(dest, e.name));
  }
  const enabled = store.get('enabled');
  enabled[manifest.id] = true;
  store.set('enabled', enabled);
  const grants = store.get('grants');
  grants[manifest.id] = manifest.permissions;
  store.set('grants', grants);
  return { ...manifest, source: 'community', enabled: true, path: dest };
}

export async function uninstallPlugin(id: string): Promise<void> {
  if (BUILT_IN_IDS.has(id)) throw new Error('Built-in plugins cannot be uninstalled — turn them off instead.');
  await fs.rm(join(pluginsDir(), id), { recursive: true, force: true });
  const enabled = store.get('enabled');
  delete enabled[id];
  store.set('enabled', enabled);
  const grants = store.get('grants');
  delete grants[id];
  store.set('grants', grants);
}

export function setPluginEnabled(id: string, on: boolean): void {
  const enabled = store.get('enabled');
  enabled[id] = on;
  store.set('enabled', enabled);
}

/** Enforcement point: does this plugin hold this permission? */
export function checkPermission(pluginId: string, permission: string): boolean {
  const grants = store.get('grants');
  const enabled = store.get('enabled');
  if (enabled[pluginId] === false) return false;
  if (BUILT_IN_IDS.has(pluginId)) {
    const meta = BUILT_IN_META.find((b) => b.id === pluginId);
    return meta?.permissions.includes(permission) ?? false;
  }
  return grants[pluginId]?.includes(permission) ?? false;
}
