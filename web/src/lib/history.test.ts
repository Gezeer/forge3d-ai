import { describe, expect, it } from "vitest";
import { HISTORY_KEY, readHistory, saveHistory, upsertHistory } from "./history";
const job = { jobId: "1", engine: "triposr", status: "queued" as const, createdAt: "2026-01-01", fileName: "chair.png" };
describe("local history", () => { it("persists and restores jobs", () => { const values = new Map<string, string>(); const storage = { getItem: (key: string) => values.get(key) || null, setItem: (key: string, value: string) => values.set(key, value) }; saveHistory([job], storage); expect(values.has(HISTORY_KEY)).toBe(true); expect(readHistory(storage)).toEqual([job]); }); it("updates without duplicating", () => expect(upsertHistory({ ...job, status: "completed" }, [job])).toEqual([{ ...job, status: "completed" }])); });
