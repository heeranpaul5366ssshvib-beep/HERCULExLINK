import { Zap, ShieldCheck, ListChecks, Play } from 'lucide-react';
import { useLocalStorage } from '@/src/hooks/useLocalStorage';
import { cn } from '@/src/utils/cn';

const GUARDRAILS = [
  { id: 'ask-before-run', title: 'Ask before running commands', description: 'HERCULE shows each shell command and waits for approval.' },
  { id: 'ask-before-delete', title: 'Ask before deleting files', description: 'Destructive file actions always need your OK.' },
  { id: 'web-confirm', title: 'Confirm before publishing anything', description: 'Posts, emails and PRs are drafted first, sent only on approval.' },
];

const LEVELS = [
  { id: 'supervised', title: 'Supervised', description: 'Every action needs approval. Best while trying things out.' },
  { id: 'assisted', title: 'Assisted', description: 'Reads and drafts freely; asks before changing anything.' },
  { id: 'autonomous', title: 'Autonomous', description: 'Works toward your goal and reports back. Guardrails still apply.' },
];

export function AutonomyView() {
  const [level, setLevel] = useLocalStorage<string>('hercule-autonomy-level', 'assisted');
  const [guardrails, setGuardrails] = useLocalStorage<Record<string, boolean>>('hercule-autonomy-guardrails', {
    'ask-before-run': true,
    'ask-before-delete': true,
    'web-confirm': true,
  });
  const [goal, setGoal] = useLocalStorage<string>('hercule-autonomy-goal', '');

  const toggleGuardrail = (id: string) => {
    setGuardrails((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  return (
    <div className="mx-auto w-full max-w-3xl px-6 py-8">
      <div className="flex items-center gap-3 mb-1">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-violet-500/10 text-violet-400 border border-violet-500/20">
          <Zap className="w-5 h-5" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-text-primary tracking-tight">Autonomy</h1>
          <p className="text-sm text-text-tertiary">Decide how independently HERCULE may act</p>
        </div>
      </div>

      <h2 className="mt-6 mb-3 text-sm font-semibold uppercase tracking-wider text-text-tertiary">Autonomy level</h2>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {LEVELS.map((l) => (
          <button
            key={l.id}
            onClick={() => setLevel(l.id)}
            className={cn(
              'card p-4 text-left transition-all',
              level === l.id ? 't-accent-border t-accent-bg-soft' : 'card-hover'
            )}
          >
            <p className={cn('font-semibold', level === l.id ? 't-accent-text' : 'text-text-primary')}>{l.title}</p>
            <p className="mt-1 text-xs text-text-tertiary">{l.description}</p>
          </button>
        ))}
      </div>

      <h2 className="mt-6 mb-3 text-sm font-semibold uppercase tracking-wider text-text-tertiary flex items-center gap-2">
        <ShieldCheck className="w-4 h-4" /> Safety guardrails
      </h2>
      <div className="space-y-2">
        {GUARDRAILS.map((g) => {
          const on = guardrails[g.id] !== false;
          return (
            <div key={g.id} className="card p-4 flex items-center gap-3">
              <div className="flex-1">
                <p className="font-medium text-text-primary text-sm">{g.title}</p>
                <p className="text-xs text-text-tertiary mt-0.5">{g.description}</p>
              </div>
              <button
                role="switch"
                aria-checked={on}
                aria-label={g.title}
                onClick={() => toggleGuardrail(g.id)}
                className={cn('relative flex-shrink-0 h-6 w-11 rounded-full transition-colors', on ? 't-toggle-on' : 'bg-slate-700')}
              >
                <span className={cn('absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all', on ? 'left-[22px]' : 'left-0.5')} />
              </button>
            </div>
          );
        })}
      </div>

      <h2 className="mt-6 mb-3 text-sm font-semibold uppercase tracking-wider text-text-tertiary flex items-center gap-2">
        <ListChecks className="w-4 h-4" /> Standing goal
      </h2>
      <div className="card p-4">
        <p className="text-xs text-text-tertiary mb-2">One ongoing objective HERCULE keeps in mind across chats.</p>
        <div className="flex gap-2">
          <input
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            placeholder='e.g. "Help me ship the portfolio site by Friday"'
            className="input t-focus"
            aria-label="Standing goal"
          />
          <button
            onClick={() => setGoal(goal.trim())}
            className="btn-primary px-4 py-2 text-sm rounded-lg flex items-center gap-1.5 flex-shrink-0"
          >
            <Play className="w-4 h-4" /> Set
          </button>
        </div>
        {goal.trim() && <p className="mt-2 text-sm text-text-secondary">Current goal: <span className="t-accent-text font-medium">{goal.trim()}</span></p>}
      </div>
    </div>
  );
}
