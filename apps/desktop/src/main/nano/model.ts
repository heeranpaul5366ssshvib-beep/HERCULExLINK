// nanoGPT-style forward mirroring models/hercule_lm/model.py (NumPy path).
// Row-major Float32 weights; math in float64 (JS numbers). Verified
// bit-faithful: identical ids, matching logits to ~1e-7 relative.
import type { NpzArray } from './npz';

export interface NanoConfig {
  hidden_size: number;
  num_layers: number;
  num_heads: number;
  ffn_size: number;
  vocab_size: number;
  context_length: number;
  norm_eps: number;
}

function matmulRows(
  X: number[][],
  W: Float32Array,
  K: number,
  N: number,
  bias: Float32Array | null
): number[][] {
  const T = X.length;
  const Y: number[][] = new Array(T);
  for (let t = 0; t < T; t++) {
    const a = X[t];
    const y = new Array<number>(N);
    for (let j = 0; j < N; j++) {
      let s = bias ? bias[j] : 0;
      for (let k = 0; k < K; k++) s += a[k] * W[k * N + j];
      y[j] = s;
    }
    Y[t] = y;
  }
  return Y;
}

function layernormRow(x: number[], gamma: Float32Array, beta: Float32Array, eps: number): number[] {
  const n = x.length;
  let mean = 0;
  for (let i = 0; i < n; i++) mean += x[i];
  mean /= n;
  let v = 0;
  for (let i = 0; i < n; i++) {
    const d = x[i] - mean;
    v += d * d;
  }
  v /= n;
  const inv = 1 / Math.sqrt(v + eps);
  const y = new Array<number>(n);
  for (let i = 0; i < n; i++) y[i] = gamma[i] * ((x[i] - mean) * inv) + beta[i];
  return y;
}

function geluRow(x: number[]): number[] {
  const c = Math.sqrt(2 / Math.PI);
  return x.map((v) => {
    const inner = c * (v + 0.044715 * v * v * v);
    return 0.5 * v * (1 + Math.tanh(inner));
  });
}

function softmaxRow(x: number[]): number[] {
  let m = -Infinity;
  for (const v of x) if (v > m) m = v;
  const e = x.map((v) => Math.exp(v - m));
  let s = 0;
  for (const v of e) s += v;
  return e.map((v) => v / s);
}

export type NanoParams = Record<string, Float32Array>;

export function paramsFromNpz(arrays: Record<string, NpzArray>): NanoParams {
  const out: NanoParams = {};
  for (const [k, v] of Object.entries(arrays)) out[k] = v.data;
  return out;
}

export interface GenerateOptions {
  maxNewTokens?: number;
  temperature?: number;
  topK?: number;
  topP?: number;
  eosId?: number;
  rng?: () => number;
  /** Called with each newly generated token id. */
  onToken?: (id: number) => void;
  /** Checked before every step; generation stops promptly when true. */
  shouldAbort?: () => boolean;
}

function tick(): Promise<void> {
  return new Promise((resolve) => setImmediate(resolve));
}

export class NanoModel {
  private p: NanoParams;
  private H: number;
  private L: number;
  private nHeads: number;
  private dh: number;
  private F: number;
  private V: number;
  readonly ctx: number;
  private eps: number;

  constructor(params: NanoParams, cfg: NanoConfig) {
    this.p = params;
    this.H = cfg.hidden_size;
    this.L = cfg.num_layers;
    this.nHeads = cfg.num_heads;
    this.dh = cfg.hidden_size / cfg.num_heads;
    this.F = cfg.ffn_size;
    this.V = cfg.vocab_size;
    this.ctx = cfg.context_length;
    this.eps = cfg.norm_eps ?? 1e-5;
  }

  private embed(ids: number[], startPos: number): number[][] {
    const { p, H } = this;
    return ids.map((id, t) => {
      const row = new Array<number>(H);
      const te = id * H;
      const pe = (startPos + t) * H;
      for (let i = 0; i < H; i++) row[i] = p.tokE[te + i] + p.posE[pe + i];
      return row;
    });
  }

  private block(x: number[][], li: number): number[][] {
    const { p, H, nHeads, dh, F } = this;
    const P = (n: string): Float32Array => p[`L${li}.${n}`];
    const T = x.length;
    const sqrtDh = Math.sqrt(dh);

    const h = x.map((r) => layernormRow(r, P('ln1W'), P('ln1b'), this.eps));
    const qkv = matmulRows(h, P('qkvW'), H, 3 * H, P('qkvb'));

    // reshape [T, H, 3*dh]: per-head q|k|v blocks (NOT interleaved)
    const q: number[][][] = [];
    const k: number[][][] = [];
    const v: number[][][] = [];
    for (let t = 0; t < T; t++) {
      const qt: number[][] = [];
      const kt: number[][] = [];
      const vt: number[][] = [];
      for (let hh = 0; hh < nHeads; hh++) {
        const base = hh * 3 * dh;
        qt.push(qkv[t].slice(base, base + dh));
        kt.push(qkv[t].slice(base + dh, base + 2 * dh));
        vt.push(qkv[t].slice(base + 2 * dh, base + 3 * dh));
      }
      q.push(qt);
      k.push(kt);
      v.push(vt);
    }

    const ctx: number[][] = [];
    for (let t = 0; t < T; t++) {
      const ct: number[] = [];
      for (let hh = 0; hh < nHeads; hh++) {
        const scores: number[] = [];
        for (let s = 0; s <= t; s++) {
          let dot = 0;
          for (let d = 0; d < dh; d++) dot += q[t][hh][d] * k[s][hh][d];
          scores.push(dot / sqrtDh);
        }
        const probs = softmaxRow(scores);
        const o = new Array<number>(dh).fill(0);
        for (let s = 0; s <= t; s++) {
          for (let d = 0; d < dh; d++) o[d] += probs[s] * v[s][hh][d];
        }
        ct.push(...o);
      }
      ctx.push(ct);
    }

    const attn = matmulRows(ctx, P('oW'), H, H, P('ob'));
    for (let t = 0; t < T; t++) for (let i = 0; i < H; i++) x[t][i] += attn[t][i];

    const h2 = x.map((r) => layernormRow(r, P('ln2W'), P('ln2b'), this.eps));
    const f1 = matmulRows(h2, P('f1W'), H, F, P('f1b'));
    const g = f1.map(geluRow);
    const f2 = matmulRows(g, P('f2W'), F, H, P('f2b'));
    for (let t = 0; t < T; t++) for (let i = 0; i < H; i++) x[t][i] += f2[t][i];
    return x;
  }

  forward(ids: number[], startPos = 0): number[][] {
    const { p, H, V } = this;
    let x = this.embed(ids, startPos);
    for (let li = 0; li < this.L; li++) x = this.block(x, li);
    const hfin = x.map((r) => layernormRow(r, p.lnfW, p.lnfb, this.eps));
    return matmulRows(hfin, p.headW, H, V, p.headb);
  }

  async generate(ids: number[], opts: GenerateOptions = {}): Promise<number[]> {
    const {
      maxNewTokens = 32,
      temperature = 0,
      topK = 0,
      topP = 1.0,
      eosId = 2,
      rng = Math.random,
      onToken,
      shouldAbort,
    } = opts;
    const out = [...ids];
    const ctx = this.ctx;
    for (let i = 0; i < maxNewTokens; i++) {
      if (shouldAbort?.()) break;
      if (out.length >= ctx) break;
      // Let /health and other requests breathe during long generations.
      if (i % 8 === 7) await tick();
      const window = out.slice(-ctx);
      const logits = this.forward(window, 0);
      const last = logits[logits.length - 1].slice();
      let nxt: number;
      if (temperature <= 0) {
        let bi = 0;
        for (let j = 1; j < last.length; j++) if (last[j] > last[bi]) bi = j;
        nxt = bi;
      } else {
        const order = last.map((_, j) => j).sort((a, b) => last[b] - last[a]);
        const keep = new Array<boolean>(last.length).fill(true);
        if (topK > 0) for (let j = topK; j < order.length; j++) keep[order[j]] = false;
        if (topP < 1.0) {
          const scaled = last.map((val) => val / Math.max(1e-6, temperature));
          const m = Math.max(...scaled);
          const exp = scaled.map((val) => Math.exp(val - m));
          const s = exp.reduce((a, b) => a + b, 0);
          const probs = exp.map((val) => val / s);
          const ranked = order.map((j) => probs[j]);
          let cum = 0;
          let cutoff = ranked.length;
          for (let j = 0; j < ranked.length; j++) {
            cum += ranked[j];
            if (cum >= topP) {
              cutoff = j + 1;
              break;
            }
          }
          for (let j = cutoff; j < order.length; j++) keep[order[j]] = false;
        }
        const masked = last.map((val, j) => (keep[j] ? val : -Infinity));
        const scaled = masked.map((val) => val / Math.max(1e-6, temperature));
        const finite = scaled.filter((val) => val > -Infinity);
        const m = Math.max(...finite);
        const exp = scaled.map((val) => (val === -Infinity ? 0 : Math.exp(val - m)));
        const s = exp.reduce((a, b) => a + b, 0);
        let r = rng() * s;
        nxt = exp.length - 1;
        for (let j = 0; j < exp.length; j++) {
          r -= exp[j];
          if (r <= 0) {
            nxt = j;
            break;
          }
        }
      }
      out.push(nxt);
      onToken?.(nxt);
      if (nxt === eosId) break;
    }
    return out;
  }
}
