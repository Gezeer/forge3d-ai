import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { TexturePanel } from "./TexturePanel";

it("shows texture action only after shape completion context renders it", () => { const generate = vi.fn(); render(<TexturePanel onGenerate={generate} onCompare={() => {}} showingTextured={false} loading={false} />); fireEvent.click(screen.getByRole("button", { name: "Gerar textura" })); expect(generate).toHaveBeenCalled(); });
it("switches between original and textured model", () => { const compare = vi.fn(); render(<TexturePanel status="textured" onGenerate={() => {}} onCompare={compare} showingTextured={false} loading={false} />); fireEvent.click(screen.getByRole("button", { name: "Texturizado" })); expect(compare).toHaveBeenCalledWith(true); });
it("renders a safe texture failure", () => { render(<TexturePanel status="texture_failed" onGenerate={() => {}} onCompare={() => {}} showingTextured={false} loading={false} />); expect(screen.getByText(/modelo branco foi preservado/i)).toBeInTheDocument(); });
