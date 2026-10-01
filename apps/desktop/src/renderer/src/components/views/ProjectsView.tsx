import { useState } from 'react';
import { FolderKanban, Plus, Trash2, Play, Pause, Check } from 'lucide-react';
import { cn } from '@/src/utils/cn';
import { useProjects, type Project } from '@/src/hooks/useWorkspace';

const STATUS_META: Record<Project['status'], { label: string; classes: string }> = {
  active: { label: 'Active', classes: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/20' },
  paused: { label: 'Paused', classes: 'bg-amber-500/15 text-amber-400 border-amber-500/20' },
  done: { label: 'Done', classes: 'bg-slate-700/60 text-text-tertiary border-border-primary' },
};

export function ProjectsView() {
  const { projects, addProject, setStatus, removeProject } = useProjects();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [showForm, setShowForm] = useState(false);

  const submit = (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!name.trim()) return;
    addProject(name, description);
    setName('');
    setDescription('');
    setShowForm(false);
  };

  return (
    <div className="mx-auto w-full max-w-3xl px-6 py-8">
      <div className="flex items-center gap-3 mb-1">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-violet-500/10 text-violet-400 border border-violet-500/20">
          <FolderKanban className="w-5 h-5" />
        </div>
        <div className="flex-1">
          <h1 className="text-2xl font-bold text-text-primary tracking-tight">Projects</h1>
          <p className="text-sm text-text-tertiary">{projects.filter((p) => p.status === 'active').length} active projects</p>
        </div>
        <button onClick={() => setShowForm(!showForm)} className="btn-primary px-4 py-2 text-sm rounded-lg flex items-center gap-1.5">
          <Plus className="w-4 h-4" /> New
        </button>
      </div>

      {showForm && (
        <form onSubmit={submit} className="card p-4 mt-6 space-y-3 animate-slide-up">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Project name"
            className="input t-focus"
            aria-label="Project name"
            autoFocus
          />
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What is this project about? (optional)"
            className="input t-focus min-h-[72px] resize-y"
            aria-label="Project description"
            rows={2}
          />
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => setShowForm(false)} className="btn-ghost px-4 py-2 text-sm rounded-lg">
              Cancel
            </button>
            <button type="submit" disabled={!name.trim()} className="btn-primary px-4 py-2 text-sm rounded-lg disabled:opacity-50">
              Create project
            </button>
          </div>
        </form>
      )}

      <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
        {projects.length === 0 && (
          <div className="card p-8 text-center sm:col-span-2">
            <FolderKanban className="w-8 h-8 mx-auto mb-2 text-text-muted" />
            <p className="text-text-secondary font-medium">No projects yet</p>
            <p className="text-sm text-text-tertiary mt-1">Create one, or ask HERCULE to "analyze my project".</p>
          </div>
        )}
        {projects.map((project) => {
          const meta = STATUS_META[project.status];
          return (
            <div key={project.id} className="card card-hover p-4 flex flex-col group">
              <div className="flex items-start justify-between gap-2 mb-2">
                <h3 className="font-semibold text-text-primary truncate">{project.name}</h3>
                <span className={cn('flex-shrink-0 px-2 py-0.5 text-xs font-medium rounded-full border', meta.classes)}>
                  {meta.label}
                </span>
              </div>
              {project.description && <p className="text-sm text-text-tertiary flex-1 line-clamp-3">{project.description}</p>}
              <div className="mt-3 pt-3 border-t border-border-primary flex items-center gap-1">
                {project.status !== 'active' && (
                  <button onClick={() => setStatus(project.id, 'active')} title="Resume" className="btn-icon p-1.5" aria-label="Resume project">
                    <Play className="w-4 h-4" />
                  </button>
                )}
                {project.status === 'active' && (
                  <button onClick={() => setStatus(project.id, 'paused')} title="Pause" className="btn-icon p-1.5" aria-label="Pause project">
                    <Pause className="w-4 h-4" />
                  </button>
                )}
                {project.status !== 'done' && (
                  <button onClick={() => setStatus(project.id, 'done')} title="Mark done" className="btn-icon p-1.5" aria-label="Mark project done">
                    <Check className="w-4 h-4" />
                  </button>
                )}
                <div className="flex-1" />
                <button
                  onClick={() => removeProject(project.id)}
                  title="Delete"
                  aria-label="Delete project"
                  className="p-1.5 rounded-lg text-text-muted opacity-0 group-hover:opacity-100 hover:text-red-400 hover:bg-red-500/10 transition-all"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
