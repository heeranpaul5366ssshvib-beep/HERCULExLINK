import { useState, useRef, useEffect, useCallback } from 'react';
import { Send, Paperclip, Plus, Zap, Search, Code, Globe, Calendar, Bot, User, MessageSquare, CheckSquare, FolderKanban, Plug, Wrench, Database, LayoutDashboard, Zap as ZapIcon } from 'lucide-react';
import { cn } from '@/utils/cn';

interface MobileChatProps {
  activeView: string;
  modelStatus: string;
  currentModel: string | null;
  onModelAction: {
    startModel: () => Promise<void>;
    stopModel: () => Promise<void>;
    installModel: () => Promise<void>;
  };
  stats: { cpu: number; ram: number; storage: number; gpu: number };
}

const QUICK_ACTIONS = [
  { label: 'Analyze', icon: Search, prompt: 'Analyze my project structure' },
  { label: 'Code', icon: Code, prompt: 'Write a React component' },
  { label: 'Search', icon: Globe, prompt: 'Search for latest AI research' },
  { label: 'Plan', icon: Calendar, prompt: 'Create a project plan' },
];

const VIEW_CONFIG = {
  chat: { icon: MessageSquare, title: 'Chat', description: 'Start a conversation with HERCULE' },
  tasks: { icon: CheckSquare, title: 'Tasks', description: 'Manage your tasks and todos' },
  projects: { icon: FolderKanban, title: 'Projects', description: 'Organize and track projects' },
  plugins: { icon: Plug, title: 'Plugins', description: 'Extend HERCULE capabilities' },
  memory: { icon: Database, title: 'Memory', description: 'Manage long-term memory' },
  tools: { icon: Wrench, title: 'Tools', description: 'Configure tools and integrations' },
  autonomy: { icon: ZapIcon, title: 'Autonomy', description: 'Configure autonomous agents' },
  home: { icon: LayoutDashboard, title: 'Home', description: 'Welcome to HERCULE' },
  settings: { icon: Wrench, title: 'Settings', description: 'Configure HERCULE settings' },
};

export function MobileChat({ activeView, modelStatus, currentModel, onModelAction, stats }: MobileChatProps) {
  const [messages, setMessages] = useState<Array<{ role: 'user' | 'assistant'; content: string }>>([
    { role: 'assistant', content: "Hi! I'm HERCULE, your local AI assistant. How can I help?" }
  ]);
  const [input, setInput] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [autoMode, setAutoMode] = useState(false);
  const [showModelInstall, setShowModelInstall] = useState(modelStatus === 'not-installed');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => { scrollToBottom(); }, [messages]);

  const sendMessage = useCallback(async (text: string) => {
    const userMessage = text.trim();
    if (!userMessage || isSending) return;

    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);
    setIsSending(true);

    setTimeout(() => {
      const responses = [
        "I've analyzed your request. Here's what I found...",
        "Let me help you with that. Based on my analysis...",
        "I'll work on this for you. Here's my approach...",
      ];
      const response = responses[Math.floor(Math.random() * responses.length)];
      setMessages(prev => [...prev, { role: 'assistant', content: response }]);
      setIsSending(false);
    }, 1500);
  }, [isSending]);

  const handleSend = useCallback(async (e?: React.FormEvent) => {
    e?.preventDefault();
    await sendMessage(input);
  }, [input, sendMessage]);

  const viewConfig = VIEW_CONFIG[activeView as keyof typeof VIEW_CONFIG] || VIEW_CONFIG.chat;

  if (activeView !== 'chat') {
    return (
      <div className="flex h-full items-center justify-center p-4">
        <div className="text-center max-w-sm">
          <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-blue-600/20 text-blue-400">
            <viewConfig.icon className="w-8 h-8" />
          </div>
          <h2 className="text-xl font-semibold mb-2">{viewConfig.title}</h2>
          <p className="text-text-tertiary mb-6">{viewConfig.description}</p>
          <div className="space-y-3 text-left">
            {Object.entries(VIEW_CONFIG).map(([key, config]) => (
              <button
                key={key}
                onClick={() => {}}
                className={cn(
                  'w-full flex items-center gap-3 px-4 py-3 rounded-xl text-left transition-all',
                  'bg-slate-800/50 border border-border-primary',
                  'hover:bg-slate-800 hover:border-border-secondary hover:text-text-primary'
                )}
              >
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-blue-500/10 text-blue-400">
                  <config.icon className="w-5 h-5" />
                </div>
                <div>
                  <p className="font-medium">{config.title}</p>
                  <p className="text-xs text-text-tertiary">{config.description}</p>
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      {showModelInstall && modelStatus === 'not-installed' && (
        <div className="mx-4 mt-4 p-4 rounded-xl bg-amber-500/10 border border-amber-500/20 animate-slide-up">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-amber-500/20">
                <Bot className="w-4 h-4 text-amber-400" />
              </div>
              <div>
                <p className="font-medium text-amber-400">Model not installed</p>
                <p className="text-sm text-text-tertiary">Install the AI model to start chatting</p>
              </div>
            </div>
            <button
              onClick={() => { onModelAction.installModel(); setShowModelInstall(false); }}
              className="btn-primary text-sm px-3 py-1.5 flex items-center gap-2"
            >
              <Bot className="w-4 h-4" />
              Install Model
            </button>
          </div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-4 space-y-4 pb-24">
        <div className="flex flex-wrap gap-2">
          {QUICK_ACTIONS.map((action, i) => (
            <button
              key={i}
              onClick={() => sendMessage(action.prompt)}
              className={cn(
                'inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-full transition-all duration-200',
                'bg-slate-800/50 text-text-secondary border border-border-primary',
                'hover:bg-slate-800 hover:text-text-primary hover:border-border-secondary',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500'
              )}
              aria-label={action.label}
            >
              <span className="flex-shrink-0"><action.icon className="w-3.5 h-3.5" /></span>
              <span>{action.label}</span>
            </button>
          ))}
        </div>

        {messages.map((message, index) => (
          <div key={index} className={cn('flex gap-3 animate-slide-up', message.role === 'user' && 'flex-row-reverse')}>
            <div className={cn(
              'flex-shrink-0 flex h-8 w-8 items-center justify-center rounded-full',
              message.role === 'user' ? 'bg-slate-700' : 'bg-gradient-to-br from-blue-600 to-violet-600'
            )}>
              {message.role === 'user' ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4 text-white" />}
            </div>
            <div className={cn('flex-1 max-w-[80%]', message.role === 'user' && 'text-right')}>
              <div className={cn(
                'inline-block px-4 py-2.5 text-sm rounded-2xl whitespace-pre-wrap break-words',
                message.role === 'user'
                  ? 'bg-blue-600 text-white rounded-tr-sm'
                  : 'bg-slate-800/50 text-text-primary border border-border-primary rounded-tl-sm'
              )}>
                {message.content}
              </div>
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      <form onSubmit={handleSend} className="fixed bottom-16 left-0 right-0 mx-4 mb-4 lg:relative lg:mb-0 lg:mx-0 lg:bottom-auto lg:mb-20">
        <div className="relative flex items-end gap-2">
          <div className="flex items-center gap-1 p-1 bg-slate-800/50 rounded-lg border border-border-primary lg:hidden">
            <button type="button" className="btn-icon p-1.5" aria-label="Attach"><Paperclip className="w-4 h-4" /></button>
            <button type="button" className="btn-icon p-1.5" aria-label="Add tool"><Plus className="w-4 h-4" /></button>
            <button
              type="button"
              onClick={() => setAutoMode(!autoMode)}
              className={cn(
                'btn-icon p-1.5 transition-all',
                autoMode ? 'text-violet-400 bg-violet-500/10' : 'text-text-tertiary hover:text-text-primary'
              )}
              aria-label="Auto mode"
            >
              <Zap className="w-4 h-4" />
            </button>
          </div>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
            placeholder="Type your message..."
            className="flex-1 min-h-[44px] max-h-48 px-4 py-3 text-sm bg-slate-900/50 text-text-primary border border-border-primary rounded-xl placeholder-text-tertiary resize-none transition-all focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20 focus:bg-slate-900 lg:rounded-2xl"
            rows={1}
            disabled={isSending}
          />
          <button
            type="submit"
            disabled={!input.trim() || isSending}
            className={cn(
              'flex-shrink-0 flex h-10 w-10 items-center justify-center rounded-xl transition-all duration-200',
              'bg-gradient-to-br from-blue-600 to-violet-600 text-white shadow-lg shadow-blue-600/25',
              'hover:from-blue-700 hover:to-violet-700 active:scale-95',
              'disabled:opacity-50 disabled:cursor-not-allowed'
            )}
            aria-label="Send message"
          >
            {isSending ? (
              <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" /></svg>
            ) : (
              <Send className="w-5 h-5" />
            )}
          </button>
        </div>
      </form>
    </div>
  );
}