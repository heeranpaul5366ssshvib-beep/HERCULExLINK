// v2.6: local-network mobile sync. Opt-in and OFF by default. When enabled,
// a small HTTP server on the LAN serves the workspace (tasks, projects,
// memories, standing goal) to a paired phone app. Pairing uses a 6-digit code
// shown in Settings; the phone exchanges it once for a bearer token.
// Nothing leaves the local network, and nothing listens unless enabled.
import { createServer, type IncomingMessage, type Server, type ServerResponse } from 'http';
import { networkInterfaces } from 'os';
import { randomBytes, randomInt, timingSafeEqual } from 'crypto';
import { existsSync, promises as fs } from 'fs';
import { join } from 'path';
import { app } from 'electron';
import Store from 'electron-store';

export interface SyncItem {
  id: string;
  updatedAt?: number;
  createdAt?: number;
  [key: string]: unknown;
}

export interface SyncSnapshot {
  tasks: SyncItem[];
  projects: SyncItem[];
  memories: SyncItem[];
  goal: string;
  goalUpdatedAt: number;
  updatedAt: number;
}

interface SyncStoreShape {
  enabled: boolean;
  pairingCode: string;
  token: string;
  lastSyncAt: number;
  failedPairs: number;
  pairLockUntil: number;
}

const store = new Store<SyncStoreShape>({
  name: 'hercule-sync',
  defaults: { enabled: false, pairingCode: '', token: '', lastSyncAt: 0, failedPairs: 0, pairLockUntil: 0 },
});

export const SYNC_PORT = 8766;

function syncFile(): string {
  return join(app.getPath('userData'), 'hercule-sync.json');
}

function emptySnapshot(): SyncSnapshot {
  return { tasks: [], projects: [], memories: [], goal: '', goalUpdatedAt: 0, updatedAt: 0 };
}

async function readSnapshot(): Promise<SyncSnapshot> {
  try {
    if (!existsSync(syncFile())) return emptySnapshot();
    const raw = JSON.parse(await fs.readFile(syncFile(), 'utf8')) as Partial<SyncSnapshot>;
    return {
      tasks: Array.isArray(raw.tasks) ? raw.tasks : [],
      projects: Array.isArray(raw.projects) ? raw.projects : [],
      memories: Array.isArray(raw.memories) ? raw.memories : [],
      goal: typeof raw.goal === 'string' ? raw.goal : '',
      goalUpdatedAt: typeof raw.goalUpdatedAt === 'number' ? raw.goalUpdatedAt : 0,
      updatedAt: typeof raw.updatedAt === 'number' ? raw.updatedAt : 0,
    };
  } catch {
    return emptySnapshot();
  }
}

async function writeSnapshot(snap: SyncSnapshot): Promise<void> {
  snap.updatedAt = Date.now();
  const file = syncFile();
  await fs.mkdir(join(file, '..'), { recursive: true });
  await fs.writeFile(file, JSON.stringify(snap, null, 2));
}

function stampOf(item: SyncItem): number {
  if (typeof item.updatedAt === 'number') return item.updatedAt;
  if (typeof item.createdAt === 'number') return item.createdAt;
  return 0;
}

/** Last-writer-wins per item id; unknown collections ignored. */
export function mergeSnapshots(base: SyncSnapshot, incoming: Partial<SyncSnapshot>): SyncSnapshot {
  const merged: SyncSnapshot = {
    tasks: mergeItems(base.tasks, incoming.tasks),
    projects: mergeItems(base.projects, incoming.projects),
    memories: mergeItems(base.memories, incoming.memories),
    goal: base.goal,
    goalUpdatedAt: base.goalUpdatedAt,
    updatedAt: Date.now(),
  };
  if (typeof incoming.goal === 'string' && typeof incoming.goalUpdatedAt === 'number') {
    if (incoming.goalUpdatedAt >= base.goalUpdatedAt && incoming.goal !== base.goal) {
      merged.goal = incoming.goal.slice(0, 500);
      merged.goalUpdatedAt = incoming.goalUpdatedAt;
    }
  }
  return merged;
}

function mergeItems(base: SyncItem[], incoming: unknown): SyncItem[] {
  if (!Array.isArray(incoming)) return base;
  const map = new Map<string, SyncItem>();
  for (const item of base) {
    if (item && typeof item.id === 'string') map.set(item.id, item);
  }
  for (const raw of incoming.slice(0, 2000)) {
    if (!raw || typeof (raw as SyncItem).id !== 'string') continue;
    const item = raw as SyncItem;
    const prev = map.get(item.id);
    if (!prev || stampOf(item) >= stampOf(prev)) map.set(item.id, item);
  }
  return [...map.values()].slice(0, 2000);
}

export function lanAddresses(): string[] {
  const out: string[] = [];
  for (const list of Object.values(networkInterfaces())) {
    for (const nic of list ?? []) {
      if (nic.family === 'IPv4' && !nic.internal) out.push(nic.address);
    }
  }
  return out;
}

export function newPairingCode(): string {
  const a = randomInt(0, 1000).toString().padStart(3, '0');
  const b = randomInt(0, 1000).toString().padStart(3, '0');
  return `${a}-${b}`;
}

function authorized(req: IncomingMessage): boolean {
  const token = store.get('token');
  if (!token) return false;
  const header = req.headers.authorization ?? '';
  const presented = Buffer.from(header.startsWith('Bearer ') ? header.slice(7) : '');
  const expected = Buffer.from(token);
  return presented.length === expected.length && timingSafeEqual(presented, expected);
}

function sendJson(res: ServerResponse, status: number, body: unknown): void {
  const data = Buffer.from(JSON.stringify(body));
  res.writeHead(status, {
    'content-type': 'application/json',
    'content-length': data.length,
    connection: 'close',
  });
  res.end(data);
}

function readBody(req: IncomingMessage, limit = 2 * 1024 * 1024): Promise<string> {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks: Buffer[] = [];
    req.on('data', (c: Buffer) => {
      size += c.length;
      if (size > limit) {
        req.destroy();
        reject(new Error('Body too large'));
        return;
      }
      chunks.push(c);
    });
    req.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
    req.on('error', reject);
  });
}

let server: Server | null = null;
let onUpdate: (() => void) | null = null;

export function setSyncUpdateListener(fn: (() => void) | null): void {
  onUpdate = fn;
}

export function isSyncEnabled(): boolean {
  return store.get('enabled');
}

export function getSyncInfo(): { enabled: boolean; addresses: string[]; port: number; pairingCode: string; paired: boolean; lastSyncAt: number } {
  return {
    enabled: store.get('enabled'),
    addresses: server ? lanAddresses() : [],
    port: SYNC_PORT,
    pairingCode: store.get('pairingCode'),
    paired: store.get('token').length > 0,
    lastSyncAt: store.get('lastSyncAt'),
  };
}

export function rotatePairingCode(): string {
  const code = newPairingCode();
  store.set('pairingCode', code);
  store.set('token', '');
  store.set('failedPairs', 0);
  store.set('pairLockUntil', 0);
  return code;
}

export async function setSyncEnabled(on: boolean): Promise<void> {
  store.set('enabled', on);
  if (on) {
    if (!store.get('pairingCode')) store.set('pairingCode', newPairingCode());
    await startSyncServer();
  } else {
    await stopSyncServer();
  }
}

export function unpairDevice(): void {
  store.set('token', '');
  store.set('failedPairs', 0);
  store.set('pairLockUntil', 0);
}

async function startSyncServer(): Promise<void> {
  if (server) return;
  const http = await import('http');
  server = http.createServer(async (req: IncomingMessage, res: ServerResponse) => {
    try {
      const url = new URL(req.url ?? '/', 'http://lan');
      if (req.method === 'GET' && url.pathname === '/v1/ping') {
        sendJson(res, 200, { ok: true, name: 'HERCULE', version: app.getVersion() });
        return;
      }
      if (req.method === 'POST' && url.pathname === '/v1/pair') {
        if (Date.now() < store.get('pairLockUntil')) {
          sendJson(res, 429, { error: 'Too many attempts — try again in a minute.' });
          return;
        }
        let body: unknown = null;
        try {
          body = JSON.parse(await readBody(req, 1024));
        } catch {
          sendJson(res, 400, { error: 'Invalid JSON' });
          return;
        }
        const code = String((body as Record<string, unknown>)?.code ?? '').trim();
        if (code && code === store.get('pairingCode')) {
          const token = randomBytes(32).toString('hex');
          store.set('token', token);
          store.set('failedPairs', 0);
          sendJson(res, 200, { token });
        } else {
          const fails = store.get('failedPairs') + 1;
          store.set('failedPairs', fails);
          if (fails >= 5) {
            store.set('pairLockUntil', Date.now() + 60000);
            store.set('failedPairs', 0);
          }
          sendJson(res, 401, { error: 'Wrong pairing code.' });
        }
        return;
      }
      if (!authorized(req)) {
        sendJson(res, 401, { error: 'Pair this device first.' });
        return;
      }
      if (req.method === 'GET' && url.pathname === '/v1/workspace') {
        sendJson(res, 200, await readSnapshot());
        return;
      }
      if (req.method === 'PUT' && url.pathname === '/v1/workspace') {
        let body: unknown = null;
        try {
          body = JSON.parse(await readBody(req));
        } catch {
          sendJson(res, 400, { error: 'Invalid JSON' });
          return;
        }
        const merged = mergeSnapshots(await readSnapshot(), (body ?? {}) as Partial<SyncSnapshot>);
        await writeSnapshot(merged);
        store.set('lastSyncAt', Date.now());
        onUpdate?.();
        sendJson(res, 200, merged);
        return;
      }
      sendJson(res, 404, { error: 'Not found' });
    } catch {
      try {
        sendJson(res, 500, { error: 'Internal error' });
      } catch {
        // socket already gone
      }
    }
  });
  await new Promise<void>((resolve, reject) => {
    server?.once('error', reject);
    // LAN-only by design: never bind public relays; pairing code gates access.
    server?.listen(SYNC_PORT, '0.0.0.0', () => resolve());
  });
}

export async function stopSyncServer(): Promise<void> {
  const s = server;
  server = null;
  if (!s) return;
  await new Promise<void>((resolve) => {
    try {
      s.close(() => resolve());
      setTimeout(resolve, 3000);
    } catch {
      resolve();
    }
  });
}

/** Called by the renderer push: merge desktop state into the shared file. */
export async function pushSnapshot(partial: Partial<SyncSnapshot>): Promise<SyncSnapshot> {
  const merged = mergeSnapshots(await readSnapshot(), partial);
  await writeSnapshot(merged);
  return merged;
}

/** Called by the renderer after a phone update: fetch the shared file. */
export async function pullSnapshot(): Promise<SyncSnapshot> {
  return readSnapshot();
}
