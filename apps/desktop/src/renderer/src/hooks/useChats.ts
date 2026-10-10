import { useCallback, useMemo } from 'react';
import { useLocalStorage } from './useLocalStorage';

// ChatGPT-style conversation memory: many sessions, each with its own
// message list, auto-titled from the first message, persisted across
// restarts. One localStorage key; useLocalStorage syncs all hook users.

export interface ChatMsg {
  role: 'user' | 'assistant';
  content: string;
}

export interface ChatSession {
  id: string;
  title: string;
  messages: ChatMsg[];
  createdAt: number;
  updatedAt: number;
  model: string | null;
}

const SESSIONS_KEY = 'hercule-chats-v1';
const ACTIVE_KEY = 'hercule-active-chat';
const MAX_SESSIONS = 50;
const MAX_MSGS = 200;
const UNTITLED = 'New chat';

export const CHAT_GREETING: ChatMsg = {
  role: 'assistant',
  content: "Hello! I'm HERCULE, your local AI assistant. How can I help you today?",
};

function newId(): string {
  return `chat_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

function autoTitle(text: string): string {
  const oneLine = text.replace(/\s+/g, ' ').trim().slice(0, 42);
  return oneLine || UNTITLED;
}

export function useChats() {
  const [sessions, setSessions] = useLocalStorage<ChatSession[]>(SESSIONS_KEY, []);
  const [activeId, setActiveId] = useLocalStorage<string | null>(ACTIVE_KEY, null);

  const sorted = useMemo(
    () => [...sessions].sort((a, b) => b.updatedAt - a.updatedAt),
    [sessions]
  );

  const active: ChatSession = useMemo(() => {
    const found = sessions.find((s) => s.id === activeId);
    if (found) return found;
    return {
      id: '__fresh__',
      title: UNTITLED,
      messages: [CHAT_GREETING],
      createdAt: Date.now(),
      updatedAt: Date.now(),
      model: null,
    };
  }, [sessions, activeId]);

  /** Persist a full message list (called debounced while streaming). */
  const saveMessages = useCallback(
    (id: string, messages: ChatMsg[]) => {
      if (id === '__fresh__') return;
      setSessions((prev) =>
        prev.map((s) =>
          s.id === id
            ? { ...s, messages: messages.slice(-MAX_MSGS), updatedAt: Date.now() }
            : s
        )
      );
    },
    [setSessions]
  );

  /** Start a chat, reusing the active one if it is still empty. */
  const newChat = useCallback(
    (model: string | null) => {
      const current = sessions.find((s) => s.id === activeId);
      if (current && current.messages.length <= 1) {
        setActiveId(current.id);
        return current.id;
      }
      const id = newId();
      const now = Date.now();
      setSessions((prev) =>
        [
          { id, title: UNTITLED, messages: [CHAT_GREETING], createdAt: now, updatedAt: now, model },
          ...prev,
        ].slice(0, MAX_SESSIONS)
      );
      setActiveId(id);
      return id;
    },
    [sessions, activeId, setSessions, setActiveId]
  );

  /** Append messages (user send / tool narration); auto-titles once. */
  const pushMessages = useCallback(
    (id: string, model: string | null, added: ChatMsg[]) => {
      if (added.length === 0) return;
      setSessions((prev) => {
        let found = false;
        const now = Date.now();
        const next = prev.map((s) => {
          if (s.id !== id) return s;
          found = true;
          const messages = [...s.messages, ...added].slice(-MAX_MSGS);
          const firstUser = s.title === UNTITLED ? added.find((m) => m.role === 'user') : undefined;
          return {
            ...s,
            messages,
            updatedAt: now,
            model: model ?? s.model,
            title: firstUser ? autoTitle(firstUser.content) : s.title,
          };
        });
        if (!found) {
          // First message of a fresh (unsaved) chat: materialize the session.
          const firstUser = added.find((m) => m.role === 'user');
          next.unshift({
            id,
            title: firstUser ? autoTitle(firstUser.content) : UNTITLED,
            messages: [CHAT_GREETING, ...added].slice(-MAX_MSGS),
            createdAt: now,
            updatedAt: now,
            model,
          });
        }
        return next.slice(0, MAX_SESSIONS);
      });
    },
    [setSessions]
  );

  /** Title an untitled chat from its first user message. */
  const ensureTitle = useCallback(
    (id: string, text: string) => {
      const title = autoTitle(text);
      if (title === UNTITLED) return;
      setSessions((prev) =>
        prev.map((s) => (s.id === id && s.title === UNTITLED ? { ...s, title } : s))
      );
    },
    [setSessions]
  );

  const renameChat = useCallback(
    (id: string, title: string) => {
      const t = title.trim().slice(0, 60);
      if (!t) return;
      setSessions((prev) => prev.map((s) => (s.id === id ? { ...s, title: t } : s)));
    },
    [setSessions]
  );

  const deleteChat = useCallback(
    (id: string) => {
      if (activeId === id) {
        const next = sessions.filter((s) => s.id !== id);
        setActiveId(next[0]?.id ?? null);
      }
      setSessions((prev) => prev.filter((s) => s.id !== id));
    },
    [activeId, sessions, setSessions, setActiveId]
  );

  return {
    sessions: sorted,
    activeId: active.id === '__fresh__' ? null : active.id,
    active,
    isFresh: active.id === '__fresh__',
    setActiveId,
    newChat,
    pushMessages,
    saveMessages,
    ensureTitle,
    renameChat,
    deleteChat,
  };
}
