import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { EngineSelector } from "./EngineSelector";
it("selects an engine accessibly", () => { const onChange = vi.fn(); render(<EngineSelector value="auto" onChange={onChange} />); fireEvent.click(screen.getByLabelText(/Hunyuan/)); expect(onChange).toHaveBeenCalledWith("hunyuan"); });
