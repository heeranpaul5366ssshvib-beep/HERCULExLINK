import { useState } from 'react';
import { Database, Plus, Trash2, Shield } from 'lucide-react';
import { useMemories } from '@/src/hooks/useWorkspace';

function formatDate(ts: number): string {
  return new Date(ts).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

export function MemoryView() {
  const { memories, addMemory, removeMemory, clearMemories } = useMemories();
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [showForm, setShowForm] = useState(false);

  const submit = (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!title.trim() && !content.trim()) return;
    addMemory(title, content);
    setTitle('');
    setContent('');
    setShowForm(false);
  };

  return (
    <div className="mx-auto w-full max-w-3xl px-6 py-8">
      <div className="flex items-center gap-3 mb-1">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-500/10 text-blue-400 border border-blue-500/20">
          <Database className="w-5 h-5" />
        </div>
        <div className="flex-1">
          <h1 className="text-2xl font-bold text-text-primary tracking-tight">Memory</h1>
          <p className="text-sm text-text-tertiary">{memories.length} long-term {memories.length === 1 ? 'memory' : 'memories'}</p>
        </div>
        <button onClick={() => setShowForm(!showForm)} className="btn-primary px-4 py-2 text-sm rounded-lg flex items-center gap-1.5">
          <Plus className="w-4 h-4" /> Remember
        </button>
      </div>

      <div className="mt-4 flex items-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-500/5 border border-emerald-500/20 text-xs text-emerald-300/90">
        <Shield className="w-4 h-4 flex-shrink-0" />
        <span>Stored only on this device. Nothing leaves your PC. HERCULE uses these to personalize answers.</span>
      </div>

      {showForm && (
        <form onSubmit={submit} className="card p-4 mt-4 space-y-3 animate-slide-up">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Title — e.g. My work stack"
            className="input t-focus"
            aria-label="Memory title"
            autoFocus
          />
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="What should HERCULE remember? e.g. I work in React + TypeScript and prefer concise answers."
            className="input t-focus min-h-[88px] resize-y"
            aria-label="Memory content"
            rows={3}
          />
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => setShowForm(false)} className="btn-ghost px-4 py-2 text-sm rounded-lg">
              Cancel
            </button>
            <button type="submit" disabled={!title.trim() && !content.trim()} className="btn-primary px-4 py-2 text-sm rounded-lg disabled:opacity-50">
              Save memory
            </button>
          </div>
        </form>
      )}

      <div className="mt-4 space-y-2">
        {memories.length === 0 && (
          <div className="card p-8 text-center">
            <Database className="w-8 h-8 mx-auto mb-2 text-text-muted" />
            <p className="text-text-secondary font-medium">No memories yet</p>
            <p className="text-sm text-text-tertiary mt-1">Save facts, preferences and context HERCULE should always know.</p>
          </div>
        )}
        {memories.map((memory) => (
          <div key={memory.id} className="card p-4 group">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h3 className="font-semibold text-text-primary">{memory.title}</h3>
                <p className="text-xs text-text-muted mt-0.5">Saved {formatDate(memory.updatedAt)}</p>
              </div>
              <button
                onClick={() => removeMemory(memory.id)}
                aria-label="Forget memory"
                className="p-1.5 flex-shrink-0 rounded-lg text-text-muted opacity-0 group-hover:opacity-100 hover:text-red-400 hover:bg-red-500/10 transition-all"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
            {memory.content && <p className="mt-2 text-sm text-text-secondary whitespace-pre-wrap">{memory.content}</p>}
          </div>
        ))}
      </div>

      {memories.length > 0 && (
        <div className="mt-4 text-right">
          <button onClick={clearMemories} className="text-xs text-text-tertiary hover:text-red-400 transition-colors">
            Forget everything
          </button>
        </div>
      )}
    </div>
  );
}
