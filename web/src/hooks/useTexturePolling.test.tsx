import { act, renderHook } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import * as api from "@/services/api";
import { useTexturePolling } from "./useTexturePolling";
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });
it("polls texture until textured", async () => { vi.useFakeTimers(); vi.spyOn(api, "getJob").mockResolvedValue({ job_id: "1", engine: "hunyuan", status: "completed", texture_status: "textured" }); const { result } = renderHook(() => useTexturePolling(100)); act(() => result.current.start("1", { job_id: "1", engine: "hunyuan", status: "completed", texture_status: "texture_queued" })); await act(async () => vi.advanceTimersByTimeAsync(100)); expect(result.current.job?.texture_status).toBe("textured"); });
