import { createWriteStream } from 'fs';
import { mkdir, existsSync } from 'fs/promises';
import { dirname, resolve } from 'path';
import https from 'https';
import http from 'http';

interface DownloadOptions {
  url: string;
  output: string;
  progress?: boolean;
}

async function downloadFile(options: DownloadOptions): Promise<void> {
  const { url, output, progress = true } = options;
  const outputDir = dirname(output);

  if (!existsSync(outputDir)) {
    await mkdir(outputDir, { recursive: true });
  }

  return new Promise((resolve, reject) => {
    const protocol = url.startsWith('https:') ? https : http;
    const request = protocol.get(url, (response) => {
      if (response.statusCode === 302 || response.statusCode === 301) {
        const redirectUrl = response.headers.location;
        if (redirectUrl) {
          downloadFile({ ...options, url: redirectUrl }).then(resolve).catch(reject);
          return;
        }
      }

      if (response.statusCode !== 200) {
        reject(new Error(`HTTP ${response.statusCode}: ${response.statusMessage}`));
        return;
      }

      const totalSize = parseInt(response.headers['content-length'] || '0', 10);
      let downloaded = 0;
      let lastProgress = -1;

      const fileStream = createWriteStream(output);

      response.on('data', (chunk) => {
        downloaded += chunk.length;
        if (progress && totalSize > 0) {
          const percent = Math.round((downloaded / totalSize) * 100);
          if (percent !== lastProgress && percent % 5 === 0) {
            process.stdout.write(`\rProgress: ${percent}%`);
            lastProgress = percent;
          }
        }
      });

      response.pipe(fileStream);

      fileStream.on('finish', () => {
        fileStream.close();
        if (progress) process.stdout.write('\n');
        resolve();
      });

      fileStream.on('error', (err) => {
        reject(err);
      });
    });

    request.on('error', (err) => {
      reject(err);
    });

    request.setTimeout(300000, () => {
      request.destroy();
      reject(new Error('Download timeout'));
    });
  });
}

async function main() {
  const args = process.argv.slice(2);
  const options: Partial<DownloadOptions> = {};

  for (let i = 0; i < args.length; i++) {
    switch (args[i]) {
      case '--url':
        options.url = args[++i];
        break;
      case '--output':
        options.output = args[++i];
        break;
      case '--progress':
        options.progress = true;
        break;
    }
  }

  if (!options.url || !options.output) {
    console.error('Usage: model-downloader --url <URL> --output <PATH> [--progress]');
    process.exit(1);
  }

  try {
    console.log(`Downloading model from ${options.url}...`);
    console.log(`Saving to ${options.output}`);
    await downloadFile(options as DownloadOptions);
    console.log('Download completed successfully!');
    process.exit(0);
  } catch (error) {
    console.error('Download failed:', error instanceof Error ? error.message : error);
    process.exit(1);
  }
}

main();