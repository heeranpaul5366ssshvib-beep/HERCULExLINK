import { useCallback } from 'react';
import { useLocalStorage, clearHerculeStorage } from './useLocalStorage';

export interface Task {
  id: string;
  title: string;
  done: boolean;
  createdAt: number;
}

export interface Project {
  id: string;
  name: string;
  description: string;
  status: 'active' | 'paused' | 'done';
  updatedAt: number;
}

export interface MemoryEntry {
  id: string;
  title: string;
  content: string;
  updatedAt: number;
}

export const WORKSPACE_KEYS = [
  'hercule-tasks',
  'hercule-projects',
  'hercule-memories',
  'hercule-plugins',
  'hercule-tools',
];

function newId(prefix: string): string {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

export function useTasks() {
  const [tasks, setTasks] = useLocalStorage<Task[]>('hercule-tasks', []);

  const addTask = useCallback(
    (title: string) => {
      const trimmed = title.trim();
      if (!trimmed) return;
      setTasks((prev) => [{ id: newId('task'), title: trimmed, done: false, createdAt: Date.now() }, ...prev]);
    },
    [setTasks]
  );

  const toggleTask = useCallback(
    (id: string) => {
      setTasks((prev) => prev.map((t) => (t.id === id ? { ...t, done: !t.done } : t)));
    },
    [setTasks]
  );

  const removeTask = useCallback(
    (id: string) => {
      setTasks((prev) => prev.filter((t) => t.id !== id));
    },
    [setTasks]
  );

  const clearDone = useCallback(() => {
    setTasks((prev) => prev.filter((t) => !t.done));
  }, [setTasks]);

  return { tasks, addTask, toggleTask, removeTask, clearDone, openCount: tasks.filter((t) => !t.done).length };
}

export function useProjects() {
  const [projects, setProjects] = useLocalStorage<Project[]>('hercule-projects', []);

  const addProject = useCallback(
    (name: string, description: string) => {
      const trimmed = name.trim();
      if (!trimmed) return;
      setProjects((prev) => [
        { id: newId('proj'), name: trimmed, description: description.trim(), status: 'active' as const, updatedAt: Date.now() },
        ...prev,
      ]);
    },
    [setProjects]
  );

  const setStatus = useCallback(
    (id: string, status: Project['status']) => {
      setProjects((prev) => prev.map((p) => (p.id === id ? { ...p, status, updatedAt: Date.now() } : p)));
    },
    [setProjects]
  );

  const removeProject = useCallback(
    (id: string) => {
      setProjects((prev) => prev.filter((p) => p.id !== id));
    },
    [setProjects]
  );

  return { projects, addProject, setStatus, removeProject };
}

export function useMemories() {
  const [memories, setMemories] = useLocalStorage<MemoryEntry[]>('hercule-memories', []);

  const addMemory = useCallback(
    (title: string, content: string) => {
      if (!title.trim() && !content.trim()) return;
      setMemories((prev) => [
        {
          id: newId('mem'),
          title: title.trim() || 'Untitled memory',
          content: content.trim(),
          updatedAt: Date.now(),
        },
        ...prev,
      ]);
    },
    [setMemories]
  );

  const removeMemory = useCallback(
    (id: string) => {
      setMemories((prev) => prev.filter((m) => m.id !== id));
    },
    [setMemories]
  );

  const clearMemories = useCallback(() => {
    setMemories([]);
  }, [setMemories]);

  return { memories, addMemory, removeMemory, clearMemories };
}

export function clearWorkspace() {
  clearHerculeStorage(WORKSPACE_KEYS);
}
