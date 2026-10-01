import { cn } from '@/src/utils/cn';
import { Bot, User, Copy, Check, ThumbsUp, ThumbsDown } from 'lucide-react';
import { useState } from 'react';

interface MessageBubbleProps {
  message: { role: 'user' | 'assistant'; content: string };
}

function TypingDots() {
  return (
    <span className="flex items-center gap-1.5 py-1" aria-label="HERCULE is thinking">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-2 w-2 rounded-full bg-text-tertiary animate-bounce"
          style={{ animationDelay: `${i * 150}ms` }}
        />
      ))}
    </span>
  );
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user';
  const [copied, setCopied] = useState(false);
  const [vote, setVote] = useState<'up' | 'down' | null>(null);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard unavailable
    }
  };

  if (isUser) {
    return (
      <div className="group flex justify-end animate-slide-up">
        <div className="flex max-w-[80%] items-end gap-2 flex-row-reverse">
          <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-slate-700 text-text-secondary">
            <User className="w-4 h-4" />
          </div>
          <div className="rounded-2xl rounded-br-md bg-slate-700/60 border border-border-primary px-4 py-2.5 text-sm text-text-primary whitespace-pre-wrap break-words">
            {message.content}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="group flex gap-3 animate-slide-up">
      <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full t-accent-gradient text-white mt-0.5">
        <Bot className="w-4 h-4" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-sm leading-7 text-text-primary whitespace-pre-wrap break-words">
          {message.content ? message.content : <TypingDots />}
        </div>
        {message.content && (
          <div className="mt-1 flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
            <button onClick={copy} className="btn-icon p-1.5" aria-label="Copy response" title="Copy">
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
            </button>
            <button
              onClick={() => setVote(vote === 'up' ? null : 'up')}
              className={cn('btn-icon p-1.5', vote === 'up' && 'text-emerald-400')}
              aria-label="Good response"
              title="Good response"
            >
              <ThumbsUp className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => setVote(vote === 'down' ? null : 'down')}
              className={cn('btn-icon p-1.5', vote === 'down' && 'text-red-400')}
              aria-label="Bad response"
              title="Bad response"
            >
              <ThumbsDown className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
