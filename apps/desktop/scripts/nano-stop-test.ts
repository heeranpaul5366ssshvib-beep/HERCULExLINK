// Tests graceful NanoServer.stop() during an active stream.
// Run bundled: must resolve quickly, not hang on keep-alive connections.
import { NanoServer } from '../src/main/nano/server';
import http from 'http';

const PORT = 8784;

async function main() {
  const server = new NanoServer(PORT);
  await server.start({
    name: 'hercule-lm-nano',
    checkpointDir:
      'C:\\Users\\hp\\HERCULE\\training\\checkpoints\\100m\\run-1790767890\\step_00005000',
    tokenizerDir: 'C:\\Users\\hp\\HERCULE\\training\\tokenizer\\hercule-bpe-nano-v1',
  });
  console.error('[test] server up');

  const data = JSON.stringify({
    messages: [{ role: 'user', content: 'Count from one to fifty slowly and carefully.' }],
    temperature: 0.7,
    stream: true,
  });
  const req = http.request(
    {
      host: '127.0.0.1',
      port: PORT,
      path: '/v1/chat/completions',
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(data) },
    },
    (res) => {
      res.on('data', () => {});
      res.on('end', () => console.error('[test] client stream ended'));
      res.on('error', () => console.error('[test] client stream error'));
    }
  );
  req.on('error', () => {});
  req.end(data);
  await new Promise((r) => setTimeout(r, 1500));

  const t0 = Date.now();
  await server.stop();
  const ms = Date.now() - t0;
  console.error(`[test] graceful stop resolved in ${ms}ms, running=${server.running}`);
  if (!server.running && ms < 10000) {
    console.error('[test] STOP TEST: PASS');
    process.exit(0);
  } else {
    console.error('[test] STOP TEST: FAIL');
    process.exit(1);
  }
}

main().catch((err) => {
  console.error('[test] FAILED:', err instanceof Error ? err.message : err);
  process.exit(1);
});
