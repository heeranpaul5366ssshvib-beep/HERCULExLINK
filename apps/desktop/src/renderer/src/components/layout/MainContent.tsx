import { useState, useRef, useEffect, useCallback } from 'react';
import { Send, Paperclip, Plus, Zap, Search, Code, Brain, CalendarCheck, ShieldCheck, Check, X, Mic, Volume2, VolumeX, Trash2 } from 'lucide-react';
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
  trimHistory,
  type ChatMessage,
} from '@/src/utils/inference';
import {
  AGENT_SYSTEM_PROMPT,
  AGENT_MAX_STEPS,
  extractToolCall,
  stripToolBlock,
  readAutonomy,
  needsApproval,
} from '@/src/utils/agent';
import { useVoice } from '@/src/hooks/useVoice';
import { useChats } from '@/src/hooks/useChats';

interface MainContentProps {
  activeView: string;
  modelStatus: string;
  currentModel: string | null;
  onModelAction: {
    startModel: () => Promise<void>;
    stopModel: () => Promise<void>;
    installModel: () => Promise<void>;
    routeMessage?: (text: string) => Promise<string | null>;
  };
  stats: { cpu: number; ram: number; storage: number; gpu: number };
  isLoading: boolean;
  ctxBudget?: number;
}

function greetingForHour(): string {
  const h = new Date().getHours();
  if (h < 5) return 'Good night';
  if (h < 12) return 'Good morning';
  if (h < 18) return 'Good afternoon';
  return 'Good evening';
}

export function MainContent({ activeView, modelStatus, currentModel, onModelAction, ctxBudget = 4096 }: MainContentProps) {
  const { chatWidth } = useTheme();
  const widthClass = CHAT_WIDTH_CLASS[chatWidth];
  const historyBudget = Math.max(256, Math.floor(ctxBudget * 0.7));
  const { active, newChat, saveMessages, ensureTitle, deleteChat } = useChats();
  const [routeNote, setRouteNote] = useState<string | null>(null);
  const routeNoteTimer = useRef<number | null>(null);
  const [agentNote, setAgentNote] = useState<string | null>(null);
  const [pendingApproval, setPendingApproval] = useState<{ tool: string; args: Record<string, unknown> } | null>(null);
  const approvalResolveRef = useRef<((ok: boolean) => void) | null>(null);
  const {
    voiceOn, setVoiceOn,
    listening, speaking, voiceError,
    supportedSTT, supportedTTS,
    startListening, stopListening, speak, stopSpeaking,
  } = useVoice();
  const voiceBaseRef = useRef('');
  const [messages, setMessages] = useState(active.messages);
  // Session switching: swap the transcript when the active chat changes.
  // Guarded by id so per-token store writes while streaming don't reset us.
  const lastChatId = useRef<string>(active.id);
  const chatSidRef = useRef<string | null>(null);
  const saveTimer = useRef<number | null>(null);
  if (lastChatId.current !== active.id) {
    lastChatId.current = active.id;
    chatSidRef.current = null;
    setMessages(active.messages);
  }
  // Persist (debounced) so history survives restarts, even mid-stream.
  useEffect(() => {
    if (saveTimer.current) window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(() => {
      const sid = chatSidRef.current ?? (active.id === '__fresh__' ? null : active.id);
      if (sid) saveMessages(sid, messages);
    }, 800);
    return () => {
      if (saveTimer.current) window.clearTimeout(saveTimer.current);
    };
  }, [messages, active.id, saveMessages]);
  const [input, setInput] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [autoMode, setAutoMode] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const toggleMic = () => {
    if (listening) {
      stopListening();
      return;
    }
    voiceBaseRef.current = input ? input + ' ' : '';
    startListening((text, final) => {
      setInput(voiceBaseRef.current + text + (final ? ' ' : ''));
    });
  };

  const toggleSpeaker = () => {
    if (speaking) stopSpeaking();
    setVoiceOn(!voiceOn);
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, activeView]);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      approvalResolveRef.current?.(false);
      approvalResolveRef.current = null;
      try {
        window.speechSynthesis?.cancel();
      } catch {
        // ignore
      }
      if (routeNoteTimer.current) window.clearTimeout(routeNoteTimer.current);
    };
  }, []);

  const settleApproval = (ok: boolean) => {
    approvalResolveRef.current?.(ok);
    approvalResolveRef.current = null;
    setPendingApproval(null);
  };

  const requestApproval = (tool: string, args: Record<string, unknown>): Promise<boolean> => {
    return new Promise((resolve) => {
      approvalResolveRef.current = resolve;
      setPendingApproval({ tool, args });
    });
  };

  // v2.3: plan-act-verify loop. The model plans (tool fence), local tools act,
  // results feed back so the model verifies/corrects, up to AGENT_MAX_STEPS.
  const runAgentTurn = useCallback(async (userMessage: string, controller: AbortController, onFinalText?: (text: string) => void) => {
    const pushAssistant = (content: string) =>
      setMessages((prev) => [...prev, { role: 'assistant' as const, content }]);
    const appendToLast = (token: string) =>
      setMessages((prev) => {
        const last = prev[prev.length - 1];
        if (!last || last.role !== 'assistant') return prev;
        return [...prev.slice(0, -1), { role: 'assistant' as const, content: last.content + token }];
      });
    const replaceLast = (content: string) =>
      setMessages((prev) => {
        if (prev.length === 0) return prev;
        return [...prev.slice(0, -1), { role: 'assistant' as const, content }];
      });

    setMessages((prev) => [...prev, { role: 'user', content: userMessage }]);
    try {
      const baseUrl = await getInferenceBaseUrl();
      const health = await checkServerHealth(baseUrl);
      if (health === 'down') {
        pushAssistant('I can\'t reach the local model server. Start a model from the Model Manager (click "Model" below), then try again.');
        return;
      }
      if (health === 'loading') {
        pushAssistant('The model is still loading into memory. Please wait a few seconds and try again.');
        return;
      }
      const startingAutonomy = readAutonomy();
      const enabledList = Object.keys(startingAutonomy.enabledTools).filter(
        (k) => startingAutonomy.enabledTools[k] !== false
      );
      const turn: ChatMessage[] = [
        {
          role: 'system',
          content:
            AGENT_SYSTEM_PROMPT +
            `\nEnabled tools: ${enabledList.join(', ') || 'none'}. Autonomy level: ${startingAutonomy.level}.`,
        },
        ...trimHistory(
          messages
            .filter((m) => m.content.trim())
            .map((m) => ({ role: m.role as 'user' | 'assistant', content: m.content })),
          historyBudget
        ),
        { role: 'user' as const, content: userMessage },
      ];

      for (let step = 1; step <= AGENT_MAX_STEPS; step++) {
        if (controller.signal.aborted) return;
        pushAssistant('');
        let full = '';
        try {
          await streamChatCompletion({
            baseUrl,
            messages: turn,
            signal: controller.signal,
            onToken: (t) => {
              full += t;
              appendToLast(t);
            },
          });
        } catch (err) {
          if (err instanceof DOMException && err.name === 'AbortError') return;
          throw err;
        }
        const call = extractToolCall(full);
        const cleaned = stripToolBlock(full);
        if (!call) {
          if (!full.trim()) {
            replaceLast('The model returned an empty response. Please try again or rephrase your message.');
          } else {
            onFinalText?.(full);
          }
          return;
        }
        turn.push({ role: 'assistant', content: full });
        const autonomy = readAutonomy();
        if (autonomy.enabledTools[call.tool] === false) {
          replaceLast(
            (cleaned ? cleaned + '\n\n' : '') +
              `⚠️ Tool "${call.tool}" is disabled in Tools — enable it to let the agent proceed.`
          );
          return;
        }
        if (typeof window === 'undefined' || !window.electronAPI?.tools) {
          replaceLast((cleaned ? cleaned + '\n\n' : '') + '⚠️ Tool execution needs the desktop app.');
          return;
        }
        setAgentNote(`Step ${step}/${AGENT_MAX_STEPS}: ${call.tool}…`);
        let approved = !needsApproval(call.tool, autonomy);
        if (!approved) approved = await requestApproval(call.tool, call.args);
        if (!approved) {
          turn.push({ role: 'user', content: `[tool ${call.tool} denied by user]` });
          pushAssistant('Understood — I skipped that tool. Tell me how to proceed.');
          return;
        }
        if (controller.signal.aborted) return;
        replaceLast((cleaned ? cleaned + '\n\n' : '') + `⚙️ Running ${call.tool}…`);
        let res: { ok: boolean; output: string; error?: string };
        try {
          res = await window.electronAPI.tools.run(call.tool, call.args);
        } catch (err) {
          res = { ok: false, output: '', error: err instanceof Error ? err.message : 'Tool failed' };
        }
        const resultText = res.ok ? res.output : `ERROR: ${res.error ?? 'failed'}`;
        turn.push({ role: 'user', content: `[tool ${call.tool} ${res.ok ? 'result' : 'error'}]\n${resultText.slice(0, 4000)}` });
        pushAssistant(
          `${res.ok ? '✅' : '❌'} ${call.tool}: ${resultText.slice(0, 300)}${resultText.length > 300 ? '…' : ''}`
        );
      }
      pushAssistant(`Stopped after ${AGENT_MAX_STEPS} steps without a final answer. Try a smaller request.`);
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      console.error('Agent turn failed:', err);
      pushAssistant('Something went wrong talking to the local model. Make sure a model is installed and running, then try again.');
    } finally {
      setAgentNote(null);
    }
  }, [messages, historyBudget]);

  const doSend = useCallback(async (text: string) => {
    const userMessage = text.trim();
    if (!userMessage || isSending) return;

    // Chat memory: pin this turn to a real session id, title if untitled.
    chatSidRef.current = active.id === '__fresh__' ? null : active.id;
    ensureTitle(chatSidRef.current ?? active.id, userMessage);

    try {
      localStorage.setItem('hercule-last-chat', String(Date.now()));
    } catch {
      // ignore storage errors
    }

    abortRef.current?.abort();
    stopSpeaking();
    if (approvalResolveRef.current) {
      approvalResolveRef.current(false);
      approvalResolveRef.current = null;
      setPendingApproval(null);
    }
    const controller = new AbortController();
    abortRef.current = controller;

    // v2.2: auto-route to the best installed model before sending.
    if (onModelAction.routeMessage) {
      try {
        const note = await onModelAction.routeMessage(userMessage);
        if (note) {
          setRouteNote(note);
          if (routeNoteTimer.current) window.clearTimeout(routeNoteTimer.current);
          routeNoteTimer.current = window.setTimeout(() => setRouteNote(null), 6000);
        }
      } catch {
        // routing never blocks the chat; fall through to the active model
      }
    }

    setInput('');
    if (autoMode) {
      setIsSending(true);
      try {
        await runAgentTurn(userMessage, controller, (t) => {
          if (voiceOn) speak(t);
        });
      } finally {
        if (abortRef.current === controller) abortRef.current = null;
        setIsSending(false);
      }
      return;
    }
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
        ...trimHistory(
          messages
            .filter((m) => m.content.trim())
            .map((m) => ({ role: m.role as 'user' | 'assistant', content: m.content })),
          historyBudget
        ),
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
      } else if (voiceOn) {
        speak(fullText);
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
  }, [isSending, messages, onModelAction, autoMode, runAgentTurn, voiceOn, speak, stopSpeaking, active.id, ensureTitle]);

  const doSendRef = useRef(doSend);
  doSendRef.current = doSend;
  const pendingSendRef = useRef<string | null>(null);

  // Fresh chat: materialize the session first, then send into it.
  useEffect(() => {
    if (pendingSendRef.current && active.id !== '__fresh__') {
      const text = pendingSendRef.current;
      pendingSendRef.current = null;
      void doSendRef.current(text);
    }
  }, [active.id]);

  const sendMessage = useCallback((text: string) => {
    const userMessage = text.trim();
    if (!userMessage || isSending) return;
    if (active.id === '__fresh__') {
      newChat(currentModel);
      pendingSendRef.current = userMessage;
      setInput('');
      return;
    }
    void doSend(userMessage);
  }, [isSending, active.id, currentModel, newChat, doSend]);

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
      {routeNote && (
        <p className="mb-2 rounded-lg border t-accent-border t-accent-bg-soft px-3 py-1.5 text-xs t-accent-text">
          {routeNote}
        </p>
      )}
      {agentNote && (
        <p className="mb-2 rounded-lg border border-violet-500/30 bg-violet-500/10 px-3 py-1.5 text-xs text-violet-300">
          ⚙️ {agentNote}
        </p>
      )}
      {(voiceError || listening) && (
        <p className="mb-2 px-1 text-[11px] text-text-tertiary">
          {listening ? '🎤 Listening… speak now.' : voiceError}
        </p>
      )}
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
            <button
              type="button"
              onClick={toggleMic}
              disabled={!supportedSTT && !listening}
              className={cn(
                'btn-icon p-1.5 transition-all rounded-lg disabled:opacity-40',
                listening
                  ? 'text-red-400 t-accent-bg-soft t-accent-border border animate-pulse'
                  : 'text-text-tertiary hover:text-text-primary'
              )}
              aria-label={listening ? 'Stop listening' : 'Voice input'}
              aria-pressed={listening}
              title={
                listening
                  ? 'Listening… click to stop'
                  : supportedSTT
                    ? 'Voice input (browser speech service, needs internet)'
                    : 'Voice input not available in this build'
              }
            >
              <Mic className="w-4 h-4" />
            </button>
            <button
              type="button"
              onClick={toggleSpeaker}
              disabled={!supportedTTS}
              className={cn(
                'btn-icon p-1.5 transition-all rounded-lg disabled:opacity-40',
                voiceOn
                  ? 't-accent-text t-accent-bg-soft t-accent-border border'
                  : 'text-text-tertiary hover:text-text-primary'
              )}
              aria-label="Read replies aloud"
              aria-pressed={voiceOn}
              title={supportedTTS ? 'Read replies aloud (on-device voice)' : 'Speech output not available in this build'}
            >
              {voiceOn ? <Volume2 className="w-4 h-4" /> : <VolumeX className="w-4 h-4" />}
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

  const chatHeader = (
    <div className="flex items-center gap-2 px-5 py-1.5 border-b border-border-primary bg-bg-secondary/60">
      <span className="text-xs font-medium text-text-secondary truncate" title={active.title}>
        {active.title}
      </span>
      <div className="flex-1" />
      <button
        onClick={() => newChat(currentModel)}
        className="flex items-center gap-1 px-2 py-1 text-xs font-medium rounded-md text-text-tertiary hover:text-text-primary hover:bg-bg-tertiary transition-colors"
        title="Start a new chat"
      >
        <Plus className="w-3.5 h-3.5" /> New
      </button>
      {!isFresh && (
        <button
          onClick={() => deleteChat(active.id)}
          className="flex items-center gap-1 px-2 py-1 text-xs font-medium rounded-md text-text-tertiary hover:text-red-400 hover:bg-red-500/10 transition-colors"
          title="Delete this chat"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      )}
    </div>
  );

  return (
    <main className="flex-1 flex flex-col overflow-hidden bg-bg-primary">
      <CapabilityStrip modelStatus={modelStatus} currentModel={currentModel} />
      {chatHeader}

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
            {pendingApproval && (
              <div className="card p-4 border-violet-500/30 animate-slide-up" role="alertdialog" aria-label="Approve tool run">
                <p className="flex items-center gap-2 text-sm font-semibold text-text-primary">
                  <ShieldCheck className="w-4 h-4 text-violet-300" />
                  Agent wants to run {pendingApproval.tool}
                </p>
                <pre className="mt-2 max-h-32 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-border-primary bg-slate-950/60 p-2 font-mono text-xs text-text-secondary">
                  {JSON.stringify(pendingApproval.args, null, 2)}
                </pre>
                <div className="mt-3 flex gap-2">
                  <button
                    onClick={() => settleApproval(true)}
                    className="btn-primary px-4 py-1.5 text-xs rounded-lg flex items-center gap-1.5"
                  >
                    <Check className="w-3.5 h-3.5" /> Approve & run
                  </button>
                  <button
                    onClick={() => settleApproval(false)}
                    className="btn-secondary px-4 py-1.5 text-xs rounded-lg flex items-center gap-1.5"
                  >
                    <X className="w-3.5 h-3.5" /> Deny
                  </button>
                </div>
              </div>
            )}
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
