export interface ChatMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

export const HERCULE_SYSTEM_PROMPT =
  'You are HERCULE, a helpful local AI assistant running entirely on the user\'s device. ' +
  'Answer clearly and concisely. Format code with markdown code blocks. ' +
  'If you do not know something, say so honestly.';

const DEFAULT_BASE_URL = 'http://127.0.0.1:8765';

export async function getInferenceBaseUrl(): Promise<string> {
  try {
    if (typeof window !== 'undefined' && window.electronAPI) {
      return await window.electronAPI.models.getServerUrl();
    }
  } catch {
    // fall through to default
  }
  return DEFAULT_BASE_URL;
}

export type ServerHealth = 'ok' | 'loading' | 'down';

export async function checkServerHealth(baseUrl: string, timeoutMs = 3000): Promise<ServerHealth> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${baseUrl}/health`, { signal: controller.signal });
    if (res.ok) return 'ok';
    if (res.status === 503) return 'loading';
    return 'down';
  } catch {
    return 'down';
  } finally {
    clearTimeout(timer);
  }
}

interface StreamOptions {
  baseUrl: string;
  messages: ChatMessage[];
  temperature?: number;
  signal?: AbortSignal;
  onToken: (token: string) => void;
}

export async function streamChatCompletion({ baseUrl, messages, temperature = 0.7, signal, onToken }: StreamOptions): Promise<string> {
  const res = await fetch(`${baseUrl}/v1/chat/completions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      messages,
      temperature,
      stream: true,
      cache_prompt: true,
    }),
    signal,
  });

  if (!res.ok || !res.body) {
    const detail = await res.text().catch(() => '');
    throw new Error(`Inference request failed (${res.status})${detail ? `: ${detail.slice(0, 200)}` : ''}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let fullText = '';

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';

    for (const rawLine of lines) {
      const line = rawLine.trim();
      if (!line.startsWith('data:')) continue;
      const payload = line.slice(5).trim();
      if (!payload || payload === '[DONE]') continue;
      try {
        const event = JSON.parse(payload);
        const token: unknown = event?.choices?.[0]?.delta?.content;
        if (typeof token === 'string' && token.length > 0) {
          fullText += token;
          onToken(token);
        }
        if (event?.choices?.[0]?.finish_reason) {
          // Stream is finishing; keep consuming until DONE.
        }
      } catch {
        // Ignore partial/invalid SSE chunks; the remainder stays buffered.
      }
    }
  }

  return fullText;
}
