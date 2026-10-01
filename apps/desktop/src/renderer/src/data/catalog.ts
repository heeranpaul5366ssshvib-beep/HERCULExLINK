export interface PluginDef {
  id: string;
  name: string;
  description: string;
  category: string;
}

export const PLUGINS: PluginDef[] = [
  { id: 'github', name: 'GitHub', description: 'Browse repos, read issues and pull requests.', category: 'Development' },
  { id: 'web', name: 'Web Search', description: 'Real-time web results to ground answers.', category: 'Research' },
  { id: 'drive', name: 'Google Drive', description: 'Read and attach your Drive documents.', category: 'Files' },
  { id: 'vscode', name: 'VS Code', description: 'Open files and diffs in your editor.', category: 'Development' },
  { id: 'terminal', name: 'Terminal', description: 'Run approved shell commands locally.', category: 'Development' },
  { id: 'files', name: 'Local Files', description: 'Search and read files in your workspace.', category: 'Files' },
  { id: 'calendar', name: 'Calendar', description: 'See upcoming events and plan around them.', category: 'Productivity' },
  { id: 'email', name: 'Email', description: 'Summarize threads and draft replies.', category: 'Productivity' },
];

export interface ToolDef {
  id: string;
  name: string;
  description: string;
  usage: string;
}

export const TOOLS: ToolDef[] = [
  { id: 'code-runner', name: 'Code Runner', description: 'Execute Python and JavaScript snippets in a sandbox.', usage: 'Ask HERCULE to "run this code"' },
  { id: 'web-fetch', name: 'Web Fetch', description: 'Fetch a URL and extract readable content.', usage: 'Paste a link and ask for a summary' },
  { id: 'file-search', name: 'File Search', description: 'Find files by name or content in your projects.', usage: '"Find where X is defined"' },
  { id: 'calculator', name: 'Calculator', description: 'Exact arithmetic, unit conversion and dates.', usage: '"What is 15% of 4,800?"' },
  { id: 'task-planner', name: 'Task Planner', description: 'Break goals into tracked steps in Tasks.', usage: '"Plan a website redesign"' },
  { id: 'memory', name: 'Long-term Memory', description: 'Remember facts across sessions, stored locally.', usage: '"Remember that I prefer…"' },
];

export interface RoadmapItem {
  title: string;
  description: string;
  status: 'planned' | 'in-progress' | 'later';
}

export const ROADMAP: RoadmapItem[] = [
  { title: 'Voice mode', description: 'Talk to HERCULE with on-device speech-to-text and TTS.', status: 'in-progress' },
  { title: 'Multi-model routing', description: 'Auto-pick the best local model per task: fast or deep.', status: 'in-progress' },
  { title: 'Plugin marketplace', description: 'One-click community plugins with sandbox permissions.', status: 'planned' },
  { title: 'Mobile sync', description: 'Encrypted local-network sync with the HERCULE phone app.', status: 'planned' },
  { title: 'Autonomous agents', description: 'Goal-driven agents that plan, act and verify multi-step work.', status: 'later' },
  { title: 'Team workspaces', description: 'Shared projects and memory with local-first collaboration.', status: 'later' },
];
