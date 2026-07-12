import { JobStatus } from "@/types/api";

export interface HistoryJob {
  jobId: string;
  engine: string;
  status: JobStatus;
  createdAt: string;
  fileName: string;
  downloadUrl?: string;
}

export const HISTORY_KEY = "forge3d-job-history-v1";
const LIMIT = 30;

export function readHistory(storage: Pick<Storage, "getItem"> = localStorage): HistoryJob[] {
  try {
    const value = JSON.parse(storage.getItem(HISTORY_KEY) || "[]");
    return Array.isArray(value) ? value.slice(0, LIMIT) : [];
  } catch {
    return [];
  }
}

export function saveHistory(jobs: HistoryJob[], storage: Pick<Storage, "setItem"> = localStorage): HistoryJob[] {
  const next = jobs.slice(0, LIMIT);
  storage.setItem(HISTORY_KEY, JSON.stringify(next));
  return next;
}

export function upsertHistory(job: HistoryJob, current: HistoryJob[]): HistoryJob[] {
  return [job, ...current.filter((item) => item.jobId !== job.jobId)].slice(0, LIMIT);
}
