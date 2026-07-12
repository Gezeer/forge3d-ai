export type Engine = "auto" | "triposr" | "hunyuan";
export type JobStatus = "queued" | "processing" | "completed" | "failed";

export interface CreateJobResponse {
  job_id: string;
  engine: Exclude<Engine, "auto">;
  status: "queued";
  status_url: string;
}

export interface JobResponse {
  job_id: string;
  engine: string;
  status: JobStatus;
  download_url?: string | null;
  error?: string | null;
  metadata?: Record<string, unknown> | null;
}

export interface HealthResponse {
  api: string;
  status: "healthy" | "degraded" | "unhealthy";
  engines: Record<string, { available: boolean; configured: boolean }>;
}

export interface ApiErrorBody {
  error?: { code?: string; message?: string; request_id?: string };
}

export class ForgeApiError extends Error {
  constructor(
    message: string,
    public readonly code = "request_error",
    public readonly requestId?: string,
    public readonly status?: number,
  ) {
    super(message);
    this.name = "ForgeApiError";
  }
}
