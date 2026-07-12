"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { getJob } from "@/services/api";
import { ForgeApiError, JobResponse } from "@/types/api";

export function useTexturePolling(interval = 2500, timeout = 30 * 60_000) {
  const [job, setJob] = useState<JobResponse | null>(null); const [error, setError] = useState<ForgeApiError | null>(null); const timer = useRef<number | null>(null); const active = useRef(false);
  const stop = useCallback(() => { active.current = false; if (timer.current) window.clearTimeout(timer.current); timer.current = null; }, []);
  const start = useCallback((jobId: string, initial: JobResponse) => { stop(); active.current = true; setJob(initial); setError(null); const deadline = Date.now() + timeout; const poll = async () => { if (!active.current) return; if (Date.now() > deadline) { setError(new ForgeApiError("A texturização excedeu o tempo esperado.", "texture_timeout")); stop(); return; } try { const next = await getJob(jobId); if (!active.current) return; setJob(next); if (next.texture_status === "textured" || next.texture_status === "texture_failed") stop(); else timer.current = window.setTimeout(poll, interval); } catch (cause) { setError(cause instanceof ForgeApiError ? cause : new ForgeApiError("Falha ao acompanhar textura.")); stop(); } }; timer.current = window.setTimeout(poll, interval); }, [interval, stop, timeout]);
  useEffect(() => stop, [stop]); return { job, error, start, stop };
}
