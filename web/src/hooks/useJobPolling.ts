"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getJob } from "@/services/api";
import { ForgeApiError, JobResponse } from "@/types/api";

const TEXTURE_TERMINAL = new Set(["completed", "failed", "textured", "texture_failed"]);

export function useJobPolling(interval = 2000, timeout = 15 * 60_000) {
  const [job, setJob] = useState<JobResponse | null>(null);
  const [error, setError] = useState<ForgeApiError | null>(null);
  const activeId = useRef<string | null>(null);
  const timer = useRef<number | null>(null);

  const stop = useCallback(() => {
    activeId.current = null;
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = null;
  }, []);

  const start = useCallback((jobId: string, initial: JobResponse) => {
    stop();
    activeId.current = jobId;
    setJob(initial);
    setError(null);
    const deadline = Date.now() + timeout;
    const poll = async () => {
      if (activeId.current !== jobId) return;
      if (Date.now() > deadline) {
        setError(new ForgeApiError("A geração demorou mais que o esperado.", "poll_timeout"));
        stop();
        return;
      }
      try {
        const next = await getJob(jobId);
        if (activeId.current !== jobId) return;
        setJob(next);
        const shapeFailed = next.status === "failed";
        const shapeOnlyCompleted = next.status === "completed" && next.engine !== "hunyuan";
        const texturedHunyuanCompleted = next.status === "completed" && next.engine === "hunyuan" && TEXTURE_TERMINAL.has(next.texture_status || "");
        if (shapeFailed || shapeOnlyCompleted || texturedHunyuanCompleted) stop();
        else timer.current = window.setTimeout(poll, interval);
      } catch (cause) {
        setError(cause instanceof ForgeApiError ? cause : new ForgeApiError("Falha ao acompanhar o job."));
        stop();
      }
    };
    timer.current = window.setTimeout(poll, interval);
  }, [interval, stop, timeout]);

  useEffect(() => stop, [stop]);
  return { job, error, start, stop, setJob };
}
