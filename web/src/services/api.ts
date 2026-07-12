import {
  ApiErrorBody,
  CreateJobResponse,
  Engine,
  ForgeApiError,
  HealthResponse,
  JobResponse,
} from "@/types/api";

const API_URL = (process.env.NEXT_PUBLIC_FORGE3D_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");
const DEFAULT_TIMEOUT = 15_000;

async function request<T>(path: string, init?: RequestInit, timeout = DEFAULT_TIMEOUT): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeout);
  try {
    const response = await fetch(`${API_URL}${path}`, { ...init, signal: controller.signal });
    const requestId = response.headers.get("X-Request-ID") || undefined;
    const body = (await response.json().catch(() => ({}))) as T & ApiErrorBody;
    if (!response.ok) {
      throw new ForgeApiError(
        body.error?.message || "Não foi possível concluir a solicitação.",
        body.error?.code,
        body.error?.request_id || requestId,
        response.status,
      );
    }
    return body;
  } catch (error) {
    if (error instanceof ForgeApiError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ForgeApiError("A solicitação excedeu o tempo limite.", "timeout");
    }
    throw new ForgeApiError("Não foi possível conectar ao Forge3D.", "network_error");
  } finally {
    window.clearTimeout(timer);
  }
}

export function createGenerationJob(file: File, engine: Engine): Promise<CreateJobResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("engine", engine);
  return request<CreateJobResponse>("/jobs/generate", { method: "POST", body: form }, 30_000);
}

export function getJob(jobId: string): Promise<JobResponse> {
  return request<JobResponse>(`/jobs/${encodeURIComponent(jobId)}`);
}

export function getDownloadUrl(jobId: string): string {
  return `${API_URL}/download/${encodeURIComponent(jobId)}`;
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/health", undefined, 5_000);
}
