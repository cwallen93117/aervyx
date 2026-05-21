import type { TaskRecord } from "./types";

export function compareTasksByDateAsc(a: TaskRecord, b: TaskRecord): number {
  const aHasDate = Boolean(a.task_date);
  const bHasDate = Boolean(b.task_date);
  if (aHasDate !== bHasDate) return aHasDate ? -1 : 1;

  if (a.task_date && b.task_date) {
    const dateComparison = a.task_date.localeCompare(b.task_date);
    if (dateComparison !== 0) return dateComparison;
  }

  return a.id - b.id;
}

export function sortTasksByDateAsc(tasks: TaskRecord[]): TaskRecord[] {
  return [...tasks].sort(compareTasksByDateAsc);
}
