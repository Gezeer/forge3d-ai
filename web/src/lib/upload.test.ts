import { describe, expect, it } from "vitest";
import { validateUpload } from "./upload";
describe("upload validation", () => { it("accepts PNG JPG and WEBP", () => { for (const type of ["image/png", "image/jpeg", "image/webp"]) expect(validateUpload(new File(["x"], "image", { type }))).toBeNull(); }); it("rejects unsupported and oversized files", () => { expect(validateUpload(new File(["x"], "x.gif", { type: "image/gif" }))).toMatch(/PNG/); expect(validateUpload(new File([new Uint8Array(21 * 1024 * 1024)], "big.png", { type: "image/png" }))).toMatch(/20 MB/); }); });
