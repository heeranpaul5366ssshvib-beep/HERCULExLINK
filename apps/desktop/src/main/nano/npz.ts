// Minimal .npz reader (ZIP64-aware, stored + deflated, '<f4' C-order only).
// Skips optimizer state (opt_*) by default.
import { readFileSync } from 'fs';
import { inflateRawSync } from 'zlib';

export interface NpzArray {
  shape: number[];
  data: Float32Array;
}

function zip64Field(extra: Buffer): number[] {
  let p = 0;
  while (p + 4 <= extra.length) {
    const id = extra.readUInt16LE(p);
    const size = extra.readUInt16LE(p + 2);
    if (id === 0x0001) {
      const vals: number[] = [];
      for (let q = p + 4; q + 8 <= p + 4 + size; q += 8) {
        vals.push(Number(extra.readBigUInt64LE(q)));
      }
      return vals;
    }
    p += 4 + size;
  }
  return [];
}

export function readNpz(filePath: string, skipPrefix = 'opt_'): Record<string, NpzArray> {
  const buf = readFileSync(filePath);
  let eocd = -1;
  for (let i = buf.length - 22; i >= 0; i--) {
    if (buf.readUInt32LE(i) === 0x06054b50) {
      eocd = i;
      break;
    }
  }
  if (eocd < 0) throw new Error('npz: no end-of-central-directory');
  const count = buf.readUInt16LE(eocd + 10);
  let off = buf.readUInt32LE(eocd + 16);
  const out: Record<string, NpzArray> = {};

  for (let n = 0; n < count; n++) {
    if (buf.readUInt32LE(off) !== 0x02014b50) throw new Error('npz: bad central header');
    const method = buf.readUInt16LE(off + 10);
    let compSize = buf.readUInt32LE(off + 24);
    const centralUncomp = buf.readUInt32LE(off + 22);
    const nameLen = buf.readUInt16LE(off + 28);
    const extraLen = buf.readUInt16LE(off + 30);
    const commentLen = buf.readUInt16LE(off + 32);
    let localOff = buf.readUInt32LE(off + 42);
    const name = buf.toString('utf8', off + 46, off + 46 + nameLen);
    const centralExtra = buf.subarray(off + 46 + nameLen, off + 46 + nameLen + extraLen);
    off += 46 + nameLen + extraLen + commentLen;
    if (!name.endsWith('.npy')) continue;
    const key = name.slice(0, -4);
    if (skipPrefix && key.startsWith(skipPrefix)) continue;

    if (localOff === 0xffffffff) {
      const vals = zip64Field(centralExtra);
      let vi = 0;
      if (centralUncomp === 0xffffffff) vi++;
      if (compSize === 0xffffffff) vi++;
      if (vi >= vals.length) throw new Error('npz: missing zip64 offset for ' + name);
      localOff = vals[vi];
    }

    const lhNameLen = buf.readUInt16LE(localOff + 26);
    const lhExtraLen = buf.readUInt16LE(localOff + 28);
    const lhExtra = buf.subarray(localOff + 30 + lhNameLen, localOff + 30 + lhNameLen + lhExtraLen);
    const dataStart = localOff + 30 + lhNameLen + lhExtraLen;
    const localComp = buf.readUInt32LE(localOff + 18);
    if (localComp === 0xffffffff) {
      const vals = zip64Field(lhExtra);
      const localUncomp = buf.readUInt32LE(localOff + 22);
      compSize = localUncomp === 0xffffffff && vals.length >= 2 ? vals[1] : vals[0];
      if (compSize === undefined) throw new Error('npz: missing zip64 sizes for ' + name);
    } else {
      compSize = localComp;
    }

    const comp = buf.subarray(dataStart, dataStart + compSize);
    // zip entries use raw DEFLATE (no zlib wrapper)
    const raw = method === 8 ? inflateRawSync(comp) : comp;

    const verMajor = raw[6];
    const hlen = verMajor === 1 ? raw.readUInt16LE(8) : raw.readUInt32LE(8);
    const hstart = verMajor === 1 ? 10 : 12;
    const header = raw.toString('ascii', hstart, hstart + hlen);
    const descr = header.match(/'descr':\s*'([^']+)'/)?.[1];
    const fortran = header.includes("'fortran_order': True");
    const shapeMatch = header.match(/'shape':\s*\(([^)]*)\)/);
    const shape = (shapeMatch?.[1] ?? '')
      .split(',')
      .map((s) => s.trim())
      .filter((s) => s.length > 0)
      .map(Number);
    if (descr !== '<f4') throw new Error(`npz: unsupported dtype ${descr} in ${name}`);
    if (fortran) throw new Error(`npz: fortran order unsupported in ${name}`);
    const floats = new Float32Array(raw.buffer, raw.byteOffset + hstart + hlen, (raw.length - hstart - hlen) / 4);
    out[key] = { shape, data: floats };
  }
  return out;
}
