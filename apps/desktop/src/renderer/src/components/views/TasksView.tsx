import { useState } from 'react';
import { CheckSquare, Plus, Trash2, Check, RotateCcw } from 'lucide-react';
import { cn } from '@/src/utils/cn';
import { useTasks } from '@/src/hooks/useWorkspace';

type Filter = 'all' | 'open' | 'done';

export function TasksView() {
  const { tasks, addTask, toggleTask, removeTask, clearDone, openCount } = useTasks();
  const [draft, setDraft] = useState('');
  const [filter, setFilter] = useState<Filter>('all');

  const visible = tasks.filter((t) => (filter === 'open' ? !t.done : filter === 'done' ? t.done : true));

  const submit = (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!draft.trim()) return;
    addTask(draft);
    setDraft('');
  };

  return (
    <div className="mx-auto w-full max-w-3xl px-6 py-8">
      <div className="flex items-center gap-3 mb-1">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
          <CheckSquare className="w-5 h-5" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-text-primary tracking-tight">Tasks</h1>
          <p className="text-sm text-text-tertiary">{openCount} open · {tasks.length - openCount} done</p>
        </div>
      </div>

      <form onSubmit={submit} className="mt-6 flex gap-2">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Add a task and press Enter…"
          className="input t-focus"
          aria-label="New task"
        />
        <button type="submit" disabled={!draft.trim()} className="btn-primary px-4 py-2 text-sm rounded-lg flex items-center gap-1.5 disabled:opacity-50">
          <Plus className="w-4 h-4" /> Add
        </button>
      </form>

      <div className="mt-4 flex items-center gap-2">
        {(['all', 'open', 'done'] as Filter[]).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={cn(
              'px-3 py-1 text-xs font-medium rounded-full border transition-colors',
              filter === f
                ? 't-nav-active'
                : 'text-text-tertiary border-border-primary hover:text-text-primary hover:bg-bg-tertiary'
            )}
          >
            {f.charAt(0).toUpperCase() + f.slice(1)}
          </button>
        ))}
        <div className="flex-1" />
        {tasks.some((t) => t.done) && (
          <button onClick={clearDone} className="text-xs text-text-tertiary hover:text-text-primary transition-colors">
            Clear completed
          </button>
        )}
      </div>

      <div className="mt-4 space-y-2">
        {visible.length === 0 && (
          <div className="card p-8 text-center">
            <RotateCcw className="w-8 h-8 mx-auto mb-2 text-text-muted" />
            <p className="text-text-secondary font-medium">Nothing here</p>
            <p className="text-sm text-text-tertiary mt-1">
              {filter === 'done' ? 'No completed tasks yet.' : 'Add your first task above, or ask HERCULE to plan something.'}
            </p>
          </div>
        )}
        {visible.map((task) => (
          <div key={task.id} className="card p-3 flex items-center gap-3 group">
            <button
              onClick={() => toggleTask(task.id)}
              aria-label={task.done ? 'Reopen task' : 'Complete task'}
              className={cn(
                'flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-md border transition-all',
                task.done
                  ? 't-toggle-on t-accent-border text-white'
                  : 'border-slate-600 hover:t-accent-border text-transparent hover:text-white/40'
              )}
            >
              <Check className="w-3.5 h-3.5" />
            </button>
            <span className={cn('flex-1 text-sm', task.done ? 'line-through text-text-muted' : 'text-text-primary')}>
              {task.title}
            </span>
            <button
              onClick={() => removeTask(task.id)}
              aria-label="Delete task"
              className="p-1.5 rounded-lg text-text-muted opacity-0 group-hover:opacity-100 hover:text-red-400 hover:bg-red-500/10 transition-all"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
