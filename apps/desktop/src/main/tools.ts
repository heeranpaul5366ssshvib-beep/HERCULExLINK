// v2.1: real local tool execution. Read-only tools only (no shell, no
// writes) so nothing here needs an approval gate — the destructive half
// (code-runner, shell) arrives with the v2.3 agent loop + Autonomy guardrails.
import { promises as fs } from 'fs';
import { join, resolve, sep } from 'path';
import { app } from 'electron';
import { lookup } from 'dns/promises';

export interface ToolResult {
  ok: boolean;
  output: string;
  error?: string;
}

// ---------------------------------------------------------------------------
// calculator: safe arithmetic, no eval(). Supports + - * / % ^ ( ) unary
// minus, decimals, constants pi/e, and single-arg math functions.
// ---------------------------------------------------------------------------

const FUNCTIONS: Record<string, (x: number) => number> = {
  sqrt: Math.sqrt, cbrt: Math.cbrt, sin: Math.sin, cos: Math.cos, tan: Math.tan,
  asin: Math.asin, acos: Math.acos, atan: Math.atan, log: Math.log, ln: Math.log,
  log10: Math.log10, exp: Math.exp, abs: Math.abs, floor: Math.floor,
  ceil: Math.ceil, round: Math.round, trunc: Math.trunc,
};

const CONSTANTS: Record<string, number> = { pi: Math.PI, e: Math.E };

class CalcParser {
  private pos = 0;
  constructor(private readonly src: string) {}

  parse(): number {
    const v = this.expr();
    this.skip();
    if (this.pos < this.src.length) throw new Error(`Unexpected '${this.src[this.pos]}'`);
    return v;
  }

  private skip() {
    while (this.pos < this.src.length && /\s/.test(this.src[this.pos] ?? '')) this.pos++;
  }

  private expr(): number {
    let v = this.term();
    for (;;) {
      this.skip();
      const c = this.src[this.pos];
      if (c === '+' || c === '-') {
        this.pos++;
        const r = this.term();
        v = c === '+' ? v + r : v - r;
      } else return v;
    }
  }

  private term(): number {
    let v = this.factor();
    for (;;) {
      this.skip();
      const c = this.src[this.pos];
      if (c === '*' || c === '/' || c === '%') {
        this.pos++;
        const r = this.factor();
        if (c === '*') v *= r;
        else if (c === '/') {
          if (r === 0) throw new Error('Division by zero');
          v /= r;
        } else {
          if (r === 0) throw new Error('Division by zero');
          v %= r;
        }
      } else return v;
    }
  }

  private factor(): number {
    let v = this.unary();
    this.skip();
    if (this.src[this.pos] === '^') {
      this.pos++;
      v = Math.pow(v, this.factor()); // right-associative
    }
    return v;
  }

  private unary(): number {
    this.skip();
    if (this.src[this.pos] === '-') {
      this.pos++;
      return -this.unary();
    }
    if (this.src[this.pos] === '+') {
      this.pos++;
      return this.unary();
    }
    return this.primary();
  }

  private primary(): number {
    this.skip();
    const c = this.src[this.pos];
    if (c === '(') {
      this.pos++;
      const v = this.expr();
      this.skip();
      if (this.src[this.pos] !== ')') throw new Error('Missing closing parenthesis');
      this.pos++;
      return v;
    }
    const num = /^[0-9]*\.?[0-9]+(?:[eE][+-]?[0-9]+)?/.exec(this.src.slice(this.pos));
    if (num) {
      this.pos += num[0].length;
      return parseFloat(num[0]);
    }
    const name = /^[a-zA-Z_][a-zA-Z0-9_]*/.exec(this.src.slice(this.pos));
    if (name) {
      this.pos += name[0].length;
      const id = name[0].toLowerCase();
      if (id in CONSTANTS) return CONSTANTS[id] as number;
      if (id in FUNCTIONS) {
        this.skip();
        if (this.src[this.pos] !== '(') throw new Error(`Expected '(' after ${id}`);
        this.pos++;
        const arg = this.expr();
        this.skip();
        if (this.src[this.pos] !== ')') throw new Error('Missing closing parenthesis');
        this.pos++;
        const fn = FUNCTIONS[id] as (x: number) => number;
        const v = fn(arg);
        if (!Number.isFinite(v)) throw new Error(`${id}() out of range`);
        return v;
      }
      throw new Error(`Unknown name '${name[0]}'`);
    }
    throw new Error(`Unexpected '${c ?? 'end of input'}'`);
  }
}

function runCalculator(args: Record<string, unknown>): ToolResult {
  const expr = String(args.expression ?? '').slice(0, 500);
  if (!expr.trim()) return { ok: false, output: '', error: 'Empty expression' };
  if (!/^[0-9+\-*/%^().,\s_a-zA-Z]+$/.test(expr)) {
    return { ok: false, output: '', error: 'Expression contains invalid characters' };
  }
  try {
    const v = new CalcParser(expr).parse();
    if (!Number.isFinite(v)) return { ok: false, output: '', error: 'Result out of range' };
    const out = Number.isInteger(v) ? String(v) : String(Math.round(v * 1e10) / 1e10);
    return { ok: true, output: out };
  } catch (err) {
    return { ok: false, output: '', error: err instanceof Error ? err.message : 'Invalid expression' };
  }
}

// ---------------------------------------------------------------------------
// file-search: substring search under one root. Sandboxed: the root must
// exist, and system locations (Windows dir, Program Files, drive roots) are
// refused. Skips binaries, deps and caches; caps depth / files / results.
// ---------------------------------------------------------------------------

const SKIP_DIRS = new Set([
  'node_modules', '.git', '.venv', 'venv', '__pycache__', '.pytest_cache',
  'dist', 'build', '.next', 'target', 'bin', 'obj', '.idea', '.vscode',
]);

const TEXT_EXTS = new Set([
  '.txt', '.md', '.markdown', '.json', '.jsonl', '.js', '.jsx', '.ts', '.tsx',
  '.py', '.java', '.c', '.h', '.cpp', '.cs', '.go', '.rs', '.rb', '.php',
  '.html', '.htm', '.css', '.scss', '.xml', '.yml', '.yaml', '.toml', '.ini',
  '.cfg', '.csv', '.tsv', '.log', '.sql', '.sh', '.ps1', '.bat', '.java',
]);

function blockedRoot(root: string): string | null {
  const norm = resolve(root).toLowerCase();
  if (/^[a-z]:\\?$/.test(norm)) return 'Drive roots are not searchable — pick a folder.';
  const windir = (process.env.SystemRoot ?? 'c:\\windows').toLowerCase();
  if (norm === windir || norm.startsWith(windir + sep)) return 'The Windows folder is off limits.';
  for (const p of ['c:\\program files', 'c:\\program files (x86)']) {
    if (norm === p || norm.startsWith(p + sep)) return 'Program Files is off limits.';
  }
  return null;
}

interface FileHit {
  path: string;
  line: number;
  text: string;
}

async function runFileSearch(args: Record<string, unknown>): Promise<ToolResult> {
  const query = String(args.query ?? '').slice(0, 200).toLowerCase();
  if (!query) return { ok: false, output: '', error: 'Empty search query' };
  let root = String(args.root ?? join(app.getPath('documents'), 'HERCULE')).slice(0, 500);
  try {
    root = resolve(root);
    const st = await fs.stat(root);
    if (!st.isDirectory()) return { ok: false, output: '', error: 'Root is not a folder' };
  } catch {
    return { ok: false, output: '', error: `Folder not found: ${root}` };
  }
  const blocked = blockedRoot(root);
  if (blocked) return { ok: false, output: '', error: blocked };

  const hits: FileHit[] = [];
  let scanned = 0;
  const MAX_FILES = 5000;
  const MAX_HITS = 50;

  async function walk(dir: string, depth: number): Promise<void> {
    if (depth > 6 || scanned >= MAX_FILES || hits.length >= MAX_HITS) return;
    let entries;
    try {
      entries = await fs.readdir(dir, { withFileTypes: true });
    } catch {
      return; // permission denied etc. — skip, never fail the whole search
    }
    for (const e of entries) {
      if (hits.length >= MAX_HITS || scanned >= MAX_FILES) return;
      if (e.name.startsWith('.') && e.name !== '.env') {
        if (SKIP_DIRS.has(e.name)) continue;
      }
      if (SKIP_DIRS.has(e.name)) continue;
      const full = join(dir, e.name);
      if (e.isDirectory()) {
        await walk(full, depth + 1);
      } else if (e.isFile()) {
        scanned++;
        const dot = e.name.lastIndexOf('.');
        const ext = dot >= 0 ? e.name.slice(dot).toLowerCase() : '';
        if (ext && !TEXT_EXTS.has(ext)) continue;
        let st;
        try {
          st = await fs.stat(full);
          if (st.size > 512 * 1024) continue;
        } catch {
          continue;
        }
        let content: string;
        try {
          const buf = await fs.readFile(full);
          if (buf.includes(0)) continue; // binary sniff
          content = buf.toString('utf8');
        } catch {
          continue;
        }
        const lines = content.split('\n');
        for (let i = 0; i < lines.length && hits.length < MAX_HITS; i++) {
          const line = lines[i] ?? '';
          if (line.toLowerCase().includes(query)) {
            hits.push({ path: full, line: i + 1, text: line.trim().slice(0, 240) });
          }
        }
      }
    }
  }

  await walk(root, 0);
  const lines = hits.map((h) => `${h.path}:${h.line}: ${h.text}`);
  const summary = `${hits.length} match${hits.length === 1 ? '' : 'es'} in ${scanned} files under ${root}`;
  return { ok: true, output: lines.length > 0 ? `${summary}\n${lines.join('\n')}` : `${summary} — no matches` };
}

// ---------------------------------------------------------------------------
// web-fetch: server-side fetch (no CORS limits) with SSRF guard: only public
// http(s) hosts; loopback / private / link-local IPs refused after DNS.
// HTML is stripped to readable text and capped.
// ---------------------------------------------------------------------------

function isPrivateIp(ip: string): boolean {
  if (ip === '::1' || ip === '::ffff:127.0.0.1') return true;
  const v4 = /^(\d+)\.(\d+)\.(\d+)\.(\d+)$/.exec(ip);
  if (v4) {
    const a = Number(v4[1]);
    const b = Number(v4[2]);
    if (a === 10 || a === 127 || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168) || a === 0) return true;
    if (a === 169 && b === 254) return true; // link-local
  } else if (ip.includes(':')) {
    const low = ip.toLowerCase();
    if (low === '::' || low.startsWith('fe80:') || low.startsWith('fc') || low.startsWith('fd')) return true;
  }
  return false;
}

async function assertPublicUrl(raw: string): Promise<URL> {
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    throw new Error('Not a valid URL');
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    throw new Error('Only http(s) URLs are allowed');
  }
  const host = url.hostname.toLowerCase();
  if (host === 'localhost' || host.endsWith('.local') || host.endsWith('.internal')) {
    throw new Error('Local network hosts are blocked');
  }
  let addrs;
  try {
    addrs = await lookup(host, { all: true });
  } catch {
    throw new Error('Could not resolve host');
  }
  if (addrs.some((a) => isPrivateIp(a.address))) {
    throw new Error('Local network hosts are blocked');
  }
  return url;
}

function htmlToText(html: string): { title: string; text: string } {
  const title = /<title[^>]*>([^<]{0,300})<\/title>/i.exec(html)?.[1]?.trim() ?? '';
  let t = html
    .replace(/<script[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style[\s\S]*?<\/style>/gi, ' ')
    .replace(/<[^>]+>/g, ' ');
  t = t
    .replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&nbsp;/g, ' ')
    .replace(/\s+/g, ' ').trim();
  return { title, text: t };
}

async function runWebFetch(args: Record<string, unknown>): Promise<ToolResult> {
  const raw = String(args.url ?? '').slice(0, 2000).trim();
  if (!raw) return { ok: false, output: '', error: 'Empty URL' };
  const maxChars = Math.min(Math.max(Number(args.maxChars ?? 8000) || 8000, 500), 40000);
  try {
    let current = await assertPublicUrl(raw);
    let res: Response | null = null;
    for (let hop = 0; hop < 5; hop++) {
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), 15000);
      try {
        res = await fetch(current.toString(), {
          redirect: 'manual',
          signal: ctrl.signal,
          headers: { 'user-agent': 'HERCULE/1.0 (local-assistant)', accept: 'text/html,text/plain,*/*' },
        });
      } finally {
        clearTimeout(timer);
      }
      if (res && res.status >= 300 && res.status < 400) {
        const loc = res.headers.get('location');
        if (!loc) break;
        current = await assertPublicUrl(new URL(loc, current).toString());
        res = null;
        continue;
      }
      break;
    }
    if (!res) return { ok: false, output: '', error: 'Too many redirects' };
    if (!res.ok) return { ok: false, output: '', error: `HTTP ${res.status}` };
    const buf = Buffer.from(await res.arrayBuffer());
    if (buf.length > 2 * 1024 * 1024) return { ok: false, output: '', error: 'Page too large (>2MB)' };
    const ctype = res.headers.get('content-type') ?? '';
    let text: string;
    let title = '';
    if (/html/i.test(ctype) || /^\s*</.test(buf.toString('utf8', 0, Math.min(buf.length, 200)))) {
      const parsed = htmlToText(buf.toString('utf8'));
      title = parsed.title;
      text = parsed.text;
    } else {
      text = buf.toString('utf8');
    }
    const truncated = text.length > maxChars;
    const head = title ? `Title: ${title}\n` : '';
    return { ok: true, output: `${head}${text.slice(0, maxChars)}${truncated ? '\n…[truncated]' : ''}` };
  } catch (err) {
    if (err instanceof Error && err.name === 'AbortError') {
      return { ok: false, output: '', error: 'Timed out after 15s' };
    }
    return { ok: false, output: '', error: err instanceof Error ? err.message : 'Fetch failed' };
  }
}

// ---------------------------------------------------------------------------
// registry + dispatcher
// ---------------------------------------------------------------------------

export interface ToolDef {
  name: string;
  description: string;
  args: string[];
}

export function listTools(): ToolDef[] {
  return [
    { name: 'calculator', description: 'Exact arithmetic: + - * / % ^, parentheses, sqrt/sin/log and more.', args: ['expression'] },
    { name: 'file-search', description: 'Substring search across text files under one folder (sandboxed).', args: ['query', 'root?'] },
    { name: 'web-fetch', description: 'Fetch a public URL and extract readable text (SSRF-guarded).', args: ['url', 'maxChars?'] },
  ];
}

export async function runTool(name: string, args: Record<string, unknown>): Promise<ToolResult> {
  switch (name) {
    case 'calculator':
      return runCalculator(args);
    case 'file-search':
      return runFileSearch(args);
    case 'web-fetch':
      return runWebFetch(args);
    default:
      return { ok: false, output: '', error: `Unknown tool '${name}'` };
  }
}
