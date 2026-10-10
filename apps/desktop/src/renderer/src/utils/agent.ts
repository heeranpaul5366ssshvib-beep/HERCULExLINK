// v2.3: plan-act-verify agent loop. Pure logic (no React) so it can be
// unit-tested in plain node. The renderer drives the loop; the model plans,
// local tools act, results feed back for verification/correction.
import { TOOLS } from '@/src/data/catalog';

export interface AgentToolCall {
  tool: string;
  args: Record<string, unknown>;
}

/** Tools safe to run without asking in assisted/autonomous modes. */
export const READ_ONLY_TOOLS = new Set(['calculator', 'file-search', 'web-fetch', 'web-search']);

export interface AutonomySnapshot {
  level: 'supervised' | 'assisted' | 'autonomous';
  guardrails: Record<string, boolean>;
  enabledTools: Record<string, boolean>;
}

export const AGENT_SYSTEM_PROMPT =
  'You are HERCULE, a local AI assistant that can use tools. ' +
  'You have these tools:\n' +
  '- calculator: {"expression": "2+2*3"} — exact arithmetic, functions like sqrt/sin/log, ^ for power.\n' +
  '- file-search: {"query": "text", "root": "optional folder"} — find text in local files.\n' +
  '- web-fetch: {"url": "https://..."} — read a public web page as text.\n' +
  '- web-search: {"query": "latest AI research papers"} — search the web, returns titles/URLs/snippets.\n' +
  'To use a tool, put EXACTLY ONE fenced block at the end of your reply:\n' +
  '```hercule-tool\n{"tool": "calculator", "args": {"expression": "15*37"}}\n```\n' +
  'Write a one-line plan before the block. After a tool result arrives, either use another tool or give the final answer with NO tool block. ' +
  'Never invent tool results. If no tool is needed, just answer directly.';

function braceMatch(src: string, start: number): string | null {
  let depth = 0;
  let inStr = false;
  let esc = false;
  for (let i = start; i < src.length; i++) {
    const c = src[i] as string;
    if (inStr) {
      if (esc) esc = false;
      else if (c === '\\') esc = true;
      else if (c === '"') inStr = false;
    } else if (c === '"') {
      inStr = true;
    } else if (c === '{') {
      depth++;
    } else if (c === '}') {
      depth--;
      if (depth === 0) return src.slice(start, i + 1);
    }
  }
  return null;
}

/** Pull a {"tool":...,"args":{...}} call out of model text. */
export function extractToolCall(text: string): AgentToolCall | null {
  const fence = /```hercule-tool\s*([\s\S]*?)```/i.exec(text);
  const candidates: string[] = [];
  if (fence?.[1]?.trim()) candidates.push(fence[1].trim());
  const looseIdx = text.indexOf('{"tool"');
  if (looseIdx >= 0) {
    const matched = braceMatch(text, looseIdx);
    if (matched) candidates.push(matched);
  }
  for (const raw of candidates) {
    try {
      const parsed: unknown = JSON.parse(raw);
      if (typeof parsed !== 'object' || parsed === null) continue;
      const rec = parsed as Record<string, unknown>;
      if (typeof rec.tool !== 'string') continue;
      if (typeof rec.args !== 'object' || rec.args === null) continue;
      return { tool: rec.tool, args: rec.args as Record<string, unknown> };
    } catch {
      // try next candidate
    }
  }
  return null;
}

/** Remove the tool fence so the chat shows the plan, not raw JSON. */
export function stripToolBlock(text: string): string {
  return text.replace(/```hercule-tool\s*[\s\S]*?```/gi, '').trim();
}

function readJson<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    if (raw === null) return fallback;
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

export function readAutonomy(): AutonomySnapshot {
  const levelRaw = readJson<string>('hercule-autonomy-level', 'assisted');
  const level = levelRaw === 'supervised' || levelRaw === 'autonomous' ? levelRaw : 'assisted';
  const guardrails = readJson<Record<string, boolean>>('hercule-autonomy-guardrails', {
    'ask-before-run': true,
    'ask-before-delete': true,
    'web-confirm': true,
  });
  const defaults: Record<string, boolean> = {};
  for (const t of TOOLS) defaults[t.id] = true;
  const enabledTools = { ...defaults, ...readJson<Record<string, boolean>>('hercule-tools', {}) };
  return { level, guardrails, enabledTools };
}

/** True when the user must approve before this tool runs. */
export function needsApproval(tool: string, autonomy: AutonomySnapshot): boolean {
  if (autonomy.enabledTools[tool] === false) return true; // disabled = treat as needing a decision
  if (autonomy.level === 'supervised') return true;
  if (!READ_ONLY_TOOLS.has(tool)) return true; // future write-capable tools always gate
  if (tool === 'web-fetch' && autonomy.guardrails['web-confirm'] === true) {
    // Reading pages is safe; publishing is what web-confirm guards (v2.5).
  }
  return false;
}

export const AGENT_MAX_STEPS = 6;
