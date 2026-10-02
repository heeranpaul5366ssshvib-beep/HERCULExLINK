// Byte-level BPE tokenizer mirroring HerculeBPETokenizer (Python).
// tokenizer.json stores non-UTF8 bytes as lone surrogates U+DC80..U+DCFF
// (Python surrogateescape); they map back to bytes 0x80..0xFF here.
import { readFileSync } from 'fs';

function strToBytes(s: string): number[] {
  const out: number[] = [];
  for (let i = 0; i < s.length; i++) {
    const c = s.charCodeAt(i);
    if (c >= 0xdc80 && c <= 0xdcff) {
      out.push(c - 0xdc00);
    } else if (c < 128) {
      out.push(c);
    } else {
      const buf = Buffer.from(s[i], 'utf8');
      for (const b of buf) out.push(b);
    }
  }
  return out;
}

function bytesKey(bytes: ArrayLike<number>): string {
  let s = '';
  for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
  return s;
}

export class NanoTokenizer {
  private vocab = new Map<string, number>();
  private inv = new Map<number, string>();
  private rank = new Map<string, number>();
  private specials = new Set<string>();

  constructor(vocab: Map<string, number>, merges: Array<[string, string]>, specials: string[]) {
    this.vocab = vocab;
    for (const [k, v] of vocab) this.inv.set(v, k);
    merges.forEach(([a, b], i) => this.rank.set(a + '\0' + b, i));
    for (const s of specials) this.specials.add(bytesKey(strToBytes(s)));
  }

  static loadFile(jsonPath: string): NanoTokenizer {
    const payload = JSON.parse(readFileSync(jsonPath, 'utf8')) as {
      vocab: Record<string, number>;
      merges: Array<[string, string]>;
      specials?: string[];
    };
    const vocab = new Map<string, number>();
    for (const [k, v] of Object.entries(payload.vocab)) {
      vocab.set(bytesKey(strToBytes(k)), v);
    }
    const merges = payload.merges.map(
      ([a, b]): [string, string] => [bytesKey(strToBytes(a)), bytesKey(strToBytes(b))]
    );
    return new NanoTokenizer(vocab, merges, payload.specials ?? []);
  }

  get bosId(): number {
    return this.vocab.get(bytesKey(strToBytes('<BOS>'))) ?? 1;
  }

  get eosId(): number {
    return this.vocab.get(bytesKey(strToBytes('<EOS>'))) ?? 2;
  }

  get unkId(): number {
    return this.vocab.get(bytesKey(strToBytes('<UNK>'))) ?? 3;
  }

  encodeWord(wordBytes: number[]): number[] {
    const whole = bytesKey(wordBytes);
    const hit = this.vocab.get(whole);
    if (hit !== undefined) return [hit];
    let parts = wordBytes.map((b) => String.fromCharCode(b));
    while (parts.length > 1) {
      let bestRank: number | null = null;
      let bestIdx = -1;
      for (let i = 0; i < parts.length - 1; i++) {
        const r = this.rank.get(parts[i] + '\0' + parts[i + 1]);
        if (r !== undefined && (bestRank === null || r < bestRank)) {
          bestRank = r;
          bestIdx = i;
        }
      }
      if (bestIdx < 0) break;
      parts = [...parts.slice(0, bestIdx), parts[bestIdx] + parts[bestIdx + 1], ...parts.slice(bestIdx + 2)];
    }
    return parts.map((p) => this.vocab.get(p) ?? this.unkId);
  }

  encode(text: string, addBos = false, addEos = false): number[] {
    const ids: number[] = [];
    if (addBos) ids.push(this.bosId);
    for (const chunk of String(text ?? '').split(/(\s+)/)) {
      if (!chunk) continue;
      ids.push(...this.encodeWord(Array.from(Buffer.from(chunk, 'utf8'))));
    }
    if (addEos) ids.push(this.eosId);
    return ids;
  }

  decode(ids: number[], skipSpecials = true): string {
    const bytes: number[] = [];
    for (const id of ids) {
      const tok = this.inv.get(Number(id));
      if (tok === undefined) continue;
      if (skipSpecials && this.specials.has(tok)) continue;
      for (let i = 0; i < tok.length; i++) bytes.push(tok.charCodeAt(i));
    }
    return new TextDecoder('utf-8').decode(Uint8Array.from(bytes));
  }
}
