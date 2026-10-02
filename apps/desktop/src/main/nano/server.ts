// Tiny OpenAI-compatible HTTP server for hercule-lm-nano checkpoints.
// Same contract as llama-server for the endpoints the app uses:
//   GET  /health                  -> {"status":"ok"} (503 while loading)
//   POST /v1/chat/completions      -> SSE stream or full JSON
// Pure Node (http/fs), no dependencies. One generation at a time.
import { createServer, type IncomingMessage, type Server, type ServerResponse } from 'http';
import { existsSync, readFileSync } from 'fs';
import { join } from 'path';
import { NanoTokenizer } from './tokenizer';
import { readNpz } from './npz';
import { NanoModel, paramsFromNpz, type NanoConfig } from './model';

export interface NanoCheckpoint {
  name: string;
  checkpointDir: string;
  tokenizerDir: string;
}

interface LoadedNano {
  model: NanoModel;
  tok: NanoTokenizer;
  ctx: number;
  eosId: number;
}

function readJson(path: string): any {
  return JSON.parse(readFileSync(path, 'utf8'));
}

function loadCheckpoint(checkpointDir: string, tokenizerDir: string): LoadedNano {
  const manifestPath = join(checkpointDir, 'manifest.json');
  const weightsPath = join(checkpointDir, 'weights.npz');
  const tokenizerPath = join(tokenizerDir, 'tokenizer.json');
  const missing: string[] = [];
  if (!existsSync(manifestPath)) missing.push('manifest.json');
  if (!existsSync(weightsPath)) missing.push('weights.npz');
  if (!existsSync(tokenizerPath)) missing.push('tokenizer.json');
  if (missing.length > 0) {
    throw new Error(
      `hercule-lm-nano checkpoint incomplete in ${checkpointDir} (missing: ${missing.join(', ')}). ` +
        `Place weights.npz + manifest.json there and the tokenizer.json under ${tokenizerDir}.`
    );
  }
  const manifest = readJson(manifestPath);
  const arch = manifest.architecture ?? manifest;
  const cfg: NanoConfig = {
    hidden_size: arch.hidden_size,
    num_layers: arch.num_layers,
    num_heads: arch.num_heads,
    ffn_size: arch.ffn_size,
    vocab_size: arch.vocab_size,
    context_length: arch.context_length,
    norm_eps: arch.norm_eps ?? 1e-5,
  };
  for (const [k, v] of Object.entries(cfg)) {
    if (typeof v !== 'number' || !Number.isFinite(v) || v <= 0) {
      throw new Error(`hercule-lm-nano manifest has an invalid ${k}.`);
    }
  }
  const tok = NanoTokenizer.loadFile(tokenizerPath);
  const params = paramsFromNpz(readNpz(weightsPath));
  const required = ['tokE', 'posE', 'lnfW', 'lnfb', 'headW', 'headb'];
  for (let li = 0; li < cfg.num_layers; li++) {
    required.push(
      `L${li}.ln1W`, `L${li}.ln1b`, `L${li}.qkvW`, `L${li}.qkvb`,
      `L${li}.oW`, `L${li}.ob`, `L${li}.ln2W`, `L${li}.ln2b`,
      `L${li}.f1W`, `L${li}.f1b`, `L${li}.f2W`, `L${li}.f2b`
    );
  }
  const absent = required.filter((k) => !params[k]);
  if (absent.length > 0) {
    throw new Error(`hercule-lm-nano weights are missing: ${absent.slice(0, 5).join(', ')}…`);
  }
  return { model: new NanoModel(params, cfg), tok, ctx: cfg.context_length, eosId: tok.eosId };
}

interface ChatMsg {
  role: string;
  content: string;
}

function buildPrompt(messages: ChatMsg[], tok: NanoTokenizer, ctx: number): number[] {
  // Nano context is tiny (64): keep the tail of the conversation only,
  // always starting with BOS. Reserve room to generate.
  const parts: string[] = [];
  for (let i = Math.max(0, messages.length - 4); i < messages.length; i++) {
    const m = messages[i];
    if (m.role === 'system') continue;
    parts.push(m.content);
  }
  let ids = tok.encode(parts.join('\n'), true, false);
  const room = Math.max(8, ctx - 16);
  if (ids.length > room) ids = ids.slice(ids.length - room);
  return ids;
}

export class NanoServer {
  private server: Server | null = null;
  private loaded: LoadedNano | null = null;
  private loading = false;
  private queue: Promise<void> = Promise.resolve();
  readonly port: number;

  constructor(port: number) {
    this.port = port;
  }

  async start(checkpoint: NanoCheckpoint): Promise<void> {
    if (this.server) return;
    this.loading = true;
    try {
      this.loaded = loadCheckpoint(checkpoint.checkpointDir, checkpoint.tokenizerDir);
    } finally {
      this.loading = false;
    }
    this.server = createServer((req: IncomingMessage, res: ServerResponse) => {
      void this.handle(req, res).catch((err) => {
        if (!res.headersSent) {
          res.writeHead(500, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: err instanceof Error ? err.message : 'nano error' }));
        } else {
          try {
            res.end();
          } catch {
            // ignore
          }
        }
      });
    });
    await new Promise<void>((resolve, reject) => {
      this.server!.once('error', reject);
      this.server!.listen(this.port, '127.0.0.1', () => {
        this.server!.removeListener('error', reject);
        resolve();
      });
    });
  }

  async stop(): Promise<void> {
    const srv = this.server;
    this.server = null;
    this.loaded = null;
    if (!srv) return;
    try {
      // Drop keep-alive SSE streams first so close() never hangs on them.
      (srv as unknown as { closeAllConnections?: () => void }).closeAllConnections?.();
    } catch {
      // older Node: fall through to close()
    }
    await new Promise<void>((resolve) => {
      srv.close(() => resolve());
      setTimeout(resolve, 3000);
    });
  }

  get running(): boolean {
    return this.server !== null;
  }

  private readBody(req: IncomingMessage): Promise<any> {
    return new Promise((resolve, reject) => {
      const chunks: Buffer[] = [];
      req.on('data', (c) => chunks.push(Buffer.isBuffer(c) ? c : Buffer.from(c)));
      req.on('end', () => {
        try {
          resolve(JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}'));
        } catch (err) {
          reject(new Error('Invalid JSON body.'));
        }
      });
      req.on('error', reject);
    });
  }

  private async handle(req: IncomingMessage, res: ServerResponse): Promise<void> {
    const url = new URL(req.url ?? '/', 'http://127.0.0.1');
    if (req.method === 'GET' && url.pathname === '/health') {
      if (!this.loaded) {
        res.writeHead(503, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ status: this.loading ? 'loading' : 'error' }));
        return;
      }
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ status: 'ok' }));
      return;
    }

    if (req.method === 'POST' && url.pathname === '/v1/chat/completions') {
      const body = await this.readBody(req);
      const loaded = this.loaded;
      if (!loaded) {
        res.writeHead(503, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'Nano model is still loading.' }));
        return;
      }
      const messages: ChatMsg[] = Array.isArray(body.messages) ? body.messages : [];
      const temperature = typeof body.temperature === 'number' ? body.temperature : 0.7;
      const stream = body.stream === true;
      const ids = buildPrompt(messages, loaded.tok, loaded.ctx);
      const maxNew = Math.max(1, loaded.ctx - ids.length);

      // If the client goes away (user sends another message, navigates),
      // stop generating promptly. Never write to a dead socket: an
      // unhandled write error here would kill the whole app.
      let clientGone = false;
      req.on('close', () => {
        clientGone = true;
      });
      res.on('error', () => {
        clientGone = true;
      });
      const alive = () => !clientGone && !res.destroyed && !res.writableEnded;
      const safeWrite = (chunk: string) => {
        if (!alive()) return false;
        try {
          res.write(chunk);
          return true;
        } catch {
          clientGone = true;
          return false;
        }
      };

      const run = async () => {
        const collected: number[] = [];
        await loaded.model.generate(ids, {
          maxNewTokens: maxNew,
          temperature: temperature <= 0 ? 0 : temperature,
          eosId: loaded.eosId,
          shouldAbort: () => clientGone,
          onToken: (id) => {
            collected.push(id);
            if (stream) {
              // Incremental decode keeps UTF-8 correct; emit only new text.
              const text = loaded.tok.decode(collected);
              const delta = text.slice(runState.sent);
              runState.sent = text.length;
              if (delta) {
                safeWrite(`data: ${JSON.stringify({ choices: [{ delta: { content: delta } }] })}\n\n`);
              }
            }
          },
        });
        return collected;
      };
      const runState = { sent: 0 };

      // Serialize generations: one at a time.
      const task = this.queue.then(run);
      this.queue = task.then(
        () => undefined,
        () => undefined
      );

      if (!stream) {
        const newIds = await task;
        if (!alive()) return;
        const text = loaded.tok.decode(newIds);
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(
          JSON.stringify({
            choices: [{ message: { role: 'assistant', content: text }, finish_reason: 'stop' }],
          })
        );
        return;
      }

      res.writeHead(200, {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        Connection: 'keep-alive',
      });
      await task;
      if (alive()) {
        safeWrite('data: [DONE]\n\n');
        res.end();
      }
      return;
    }

    res.writeHead(404, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'Not found. Nano engine serves /health and /v1/chat/completions.' }));
  }
}
