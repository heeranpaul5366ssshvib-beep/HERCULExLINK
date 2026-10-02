// Standalone nano server for testing: `node nano-serve.cjs <port>`
// Uses the real local checkpoint + tokenizer.
import { NanoServer } from '../src/main/nano/server';

const port = parseInt(process.argv[2] ?? '8782', 10);
const server = new NanoServer(port);

async function main() {
  await server.start({
    name: 'hercule-lm-nano',
    checkpointDir:
      'C:\\Users\\hp\\HERCULE\\training\\checkpoints\\100m\\run-1790767890\\step_00005000',
    tokenizerDir: 'C:\\Users\\hp\\HERCULE\\training\\tokenizer\\hercule-bpe-nano-v1',
  });
  console.error(`[nano-serve] listening on 127.0.0.1:${port}`);
  const shutdown = async () => {
    await server.stop();
    process.exit(0);
  };
  process.on('SIGTERM', shutdown);
  process.on('SIGINT', shutdown);
}

main().catch((err) => {
  console.error('[nano-serve] FAILED:', err instanceof Error ? err.message : err);
  process.exit(1);
});
