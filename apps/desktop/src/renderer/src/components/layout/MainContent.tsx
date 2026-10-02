import { useState, useRef, useEffect, useCallback } from 'react';
import { Send, Paperclip, Plus, Zap, Search, Code, Brain, CalendarCheck } from 'lucide-react';
import { cn } from '@/src/utils/cn';
import { QuickActionPill } from '@/src/components/chat/QuickActionPill';
import { MessageBubble } from '@/src/components/chat/MessageBubble';
import { ModelSelector } from '@/src/components/layout/ModelSelector';
import { CapabilityStrip } from '@/src/components/layout/CapabilityStrip';
import { TasksView } from '@/src/components/views/TasksView';
import { ProjectsView } from '@/src/components/views/ProjectsView';
import { MemoryView } from '@/src/components/views/MemoryView';
import { ToolsView } from '@/src/components/views/ToolsView';
import { PluginsView } from '@/src/components/views/PluginsView';
import { AutonomyView } from '@/src/components/views/AutonomyView';
import { SettingsView } from '@/src/components/views/SettingsView';
import { useTheme, CHAT_WIDTH_CLASS } from '@/src/context/ThemeContext';
import {
  HERCULE_SYSTEM_PROMPT,
  checkServerHealth,
  getInferenceBaseUrl,
  streamChatCompletion,
  type ChatMessage,
} from '@/src/utils/inference';

interface MainContentProps {
  activeView: string;
  modelStatus: string;
  currentModel: string | null;
  onModelAction: {
    startModel: () => Promise<void>;
    stopModel: () => Promise<void>;
    installModel: () => Promise<void>;
  };
  stats: { cpu: number; ram: number; storage: number; gpu: number };
  isLoading: boolean;
}

function greetingForHour(): string {
  const h = new Date().getHours();
  if (h < 5) return 'Good night';
  if (h < 12) return 'Good morning';
  if (h < 18) return 'Good afternoon';
  return 'Good evening';
}

export function MainContent({ activeView, modelStatus, currentModel }: MainContentProps) {
  const { chatWidth } = useTheme();
  const widthClass = CHAT_WIDTH_CLASS[chatWidth];
  const [messages, setMessages] = useState<Array<{ role: 'user' | 'assistant'; content: string }>>([
    { role: 'assistant', content: "Hello! I'm HERCULE, your local AI assistant. How can I help you today?" }
  ]);
  const [input, setInput] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [autoMode, setAutoMode] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, activeView]);

  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  const sendMessage = useCallback(async (text: string) => {
    const userMessage = text.trim();
    if (!userMessage || isSending) return;

    try {
      localStorage.setItem('hercule-last-chat', String(Date.now()));
    } catch {
      // ignore storage errors
    }

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: userMessage }, { role: 'assistant', content: '' }]);
    setIsSending(true);

    const appendToken = (token: string) => {
      setMessages(prev => {
        const last = prev[prev.length - 1];
        if (!last || last.role !== 'assistant') return prev;
        return [...prev.slice(0, -1), { role: 'assistant' as const, content: last.content + token }];
      });
    };

    const replaceLastMessage = (content: string) => {
      setMessages(prev => {
        if (prev.length === 0) return prev;
        return [...prev.slice(0, -1), { role: 'assistant' as const, content }];
      });
    };

    try {
      const baseUrl = await getInferenceBaseUrl();
      const health = await checkServerHealth(baseUrl);
      if (health === 'down') {
        replaceLastMessage(
          'I can\'t reach the local model server. Start a model from the Model Manager (click "Model" below), then try again.'
        );
        return;
      }
      if (health === 'loading') {
        replaceLastMessage('The model is still loading into memory. Please wait a few seconds and try again.');
        return;
      }

      const history: ChatMessage[] = [
        { role: 'system', content: HERCULE_SYSTEM_PROMPT },
        ...messages.map(m => ({ role: m.role, content: m.content })),
        { role: 'user' as const, content: userMessage },
      ];

      const fullText = await streamChatCompletion({
        baseUrl,
        messages: history,
        signal: controller.signal,
        onToken: appendToken,
      });

      if (!fullText.trim()) {
        replaceLastMessage('The model returned an empty response. Please try again or rephrase your message.');
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      console.error('Inference failed:', err);
      replaceLastMessage(
        'Something went wrong talking to the local model. Make sure a model is installed and running, then try again.'
      );
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      setIsSending(false);
    }
  }, [isSending, messages]);

  const handleSend = async (e?: React.FormEvent) => {
    e?.preventDefault();
    await sendMessage(input);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const quickActions = [
    { label: 'Analyze my project', icon: <Search className="w-4 h-4" />, prompt: 'Analyze my project structure and suggest improvements' },
    { label: 'Write some code', icon: <Code className="w-4 h-4" />, prompt: 'Write a React component for a dashboard widget' },
    { label: 'Search the web', icon: <Brain className="w-4 h-4" />, prompt: 'Search for latest AI research papers' },
    { label: 'Plan a task', icon: <CalendarCheck className="w-4 h-4" />, prompt: 'Create a project plan for a new feature' },
  ];

  const inputBar = (
    <div className={`mx-auto w-full ${widthClass} px-4 pb-3`}>
      <div className="flex flex-wrap gap-2 mb-3">
        {quickActions.map((action, i) => (
          <QuickActionPill key={i} label={action.label} icon={action.icon} onClick={() => sendMessage(action.prompt)} />
        ))}
      </div>

      <form onSubmit={handleSend} className="relative">
        <div className="rounded-2xl border border-border-primary bg-slate-900/70 backdrop-blur-sm transition-all focus-within:t-accent-border focus-within:t-accent-ring">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={modelStatus === 'running' ? 'Message HERCULE…' : 'Start a model to begin chatting…'}
            className="w-full min-h-[52px] max-h-48 px-4 pt-3 pb-1 text-sm bg-transparent text-text-primary placeholder-text-tertiary resize-none focus:outline-none"
            rows={1}
            disabled={isSending}
            aria-label="Message input"
          />
          <div className="flex items-center gap-1 px-2 pb-2">
            <button
              type="button"
              className="btn-icon p-1.5 text-text-tertiary hover:text-text-primary"
              aria-label="Attach file"
              title="Attach file (coming soon)"
            >
              <Paperclip className="w-4 h-4" />
            </button>
            <button
              type="button"
              className="btn-icon p-1.5 text-text-tertiary hover:text-text-primary"
              aria-label="Add tool"
              title="Tools (coming soon)"
            >
              <Plus className="w-4 h-4" />
            </button>
            <button
              type="button"
              onClick={() => setAutoMode(!autoMode)}
              className={cn(
                'btn-icon p-1.5 transition-all rounded-lg',
                autoMode
                  ? 't-accent-text t-accent-bg-soft t-accent-border border'
                  : 'text-text-tertiary hover:text-text-primary'
              )}
              aria-label="Auto mode"
              aria-pressed={autoMode}
              title="Auto mode: let HERCULE chain tools automatically"
            >
              <Zap className="w-4 h-4" />
            </button>
            <div className="flex-1" />
            <span className="hidden sm:block text-[11px] text-text-muted mr-1">Enter to send · Shift+Enter for new line</span>
            <ModelSelector currentStatus={modelStatus} />
            <button
              type="submit"
              disabled={!input.trim() || isSending}
              className={cn(
                'flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl text-white transition-all duration-200',
                't-send-btn active:scale-95 disabled:opacity-40 disabled:cursor-not-allowed disabled:saturate-50'
              )}
              aria-label="Send message"
            >
              {isSending ? (
                <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" /></svg>
              ) : (
                <Send className="w-4 h-4" />
              )}
            </button>
          </div>
        </div>
      </form>
      <p className="mt-2 text-center text-[11px] text-text-muted">
        HERCULE runs 100% locally. Models can make mistakes — verify important answers.
      </p>
    </div>
  );

  const renderView = () => {
    switch (activeView) {
      case 'tasks':
        return <TasksView />;
      case 'projects':
        return <ProjectsView />;
      case 'memory':
        return <MemoryView />;
      case 'tools':
        return <ToolsView />;
      case 'plugins':
        return <PluginsView />;
      case 'autonomy':
        return <AutonomyView />;
      case 'settings':
        return <SettingsView modelStatus={modelStatus} currentModel={currentModel} />;
      case 'chat':
      case 'home':
      default:
        return null;
    }
  };

  const otherView = renderView();
  if (otherView) {
    return (
      <main className="flex-1 flex flex-col overflow-hidden bg-bg-primary">
        <CapabilityStrip modelStatus={modelStatus} currentModel={currentModel} />
        <div className="flex-1 overflow-y-auto">{otherView}</div>
      </main>
    );
  }

  const isFresh = messages.length <= 1;

  return (
    <main className="flex-1 flex flex-col overflow-hidden bg-bg-primary">
      <CapabilityStrip modelStatus={modelStatus} currentModel={currentModel} />

      <div className="flex-1 overflow-y-auto">
        {isFresh ? (
          <div className={`mx-auto flex min-h-full w-full ${widthClass} flex-col items-center justify-center px-6 py-10 text-center`}>
            <div className="flex h-14 w-14 items-center justify-center rounded-2xl t-accent-gradient text-white shadow-lg mb-5">
              <Brain className="w-7 h-7" />
            </div>
            <h1 className="text-3xl md:text-4xl font-bold text-text-primary tracking-tight">
              {greetingForHour()}, HERCULE
            </h1>
            <p className="mt-2 text-text-secondary">
              {modelStatus === 'running'
                ? `Your local ${currentModel ?? 'model'} is ready. What shall we work on?`
                : 'Start a model below, then ask anything — privately, offline, on this PC.'}
            </p>
            <div className="mt-8 grid w-full grid-cols-1 sm:grid-cols-2 gap-3 text-left">
              {quickActions.map((action, i) => (
                <button
                  key={i}
                  onClick={() => sendMessage(action.prompt)}
                  className="card card-hover p-4 flex items-start gap-3"
                >
                  <span className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg t-accent-bg-soft t-accent-text">
                    {action.icon}
                  </span>
                  <span>
                    <span className="block font-medium text-text-primary text-sm">{action.label}</span>
                    <span className="block text-xs text-text-tertiary mt-0.5 line-clamp-1">{action.prompt}</span>
                  </span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className={`mx-auto w-full ${widthClass} px-4 py-6 chat-list`}>
            {messages.map((message, index) => (
              <MessageBubble key={index} message={message} />
            ))}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      <div className="border-t border-border-primary bg-bg-primary/95 backdrop-blur-sm pt-3">
        {inputBar}
      </div>
    </main>
  );
}
