// Smoke test for the in-app nano engine: loads a real checkpoint,
// serves HTTP, runs a chat completion. Run: pnpm exec tsx scripts/nano-smoke.ts
import { NanoServer } from '../src/main/nano/server';

const CHECKPOINT = {
  name: 'hercule-lm-nano',
  checkpointDir:
    'C:\\Users\\hp\\HERCULE\\training\\checkpoints\\100m\\run-1790767890\\step_00005000',
  tokenizerDir: 'C:\\Users\\hp\\HERCULE\\training\\tokenizer\\hercule-bpe-nano-v1',
};
const PORT = 8781;

async function main() {
  const t0 = Date.now();
  const server = new NanoServer(PORT);
  await server.start(CHECKPOINT);
  console.log(`load: ${Date.now() - t0}ms`);

  const health = await fetch(`http://127.0.0.1:${PORT}/health`).then((r) => r.json());
  console.log('health:', JSON.stringify(health));

  const t1 = Date.now();
  const res = await fetch(`http://127.0.0.1:${PORT}/v1/chat/completions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      messages: [{ role: 'user', content: 'Hello, how are you?' }],
      temperature: 0,
      stream: false,
    }),
  });
  const data = await res.json();
  console.log(`chat: ${Date.now() - t1}ms status=${res.status}`);
  console.log('reply:', JSON.stringify(data?.choices?.[0]?.message?.content));

  // Streaming path (what the chat UI uses)
  const t2 = Date.now();
  const sse = await fetch(`http://127.0.0.1:${PORT}/v1/chat/completions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      messages: [{ role: 'user', content: '2+2=' }],
      temperature: 0,
      stream: true,
    }),
  });
  const text = await sse.text();
  console.log(`stream: ${Date.now() - t2}ms`);
  console.log('sse tail:', JSON.stringify(text.slice(-120)));

  await server.stop();
  console.log('stopped');
}

main().catch((err) => {
  console.error('SMOKE FAIL:', err instanceof Error ? err.message : err);
  process.exit(1);
});
