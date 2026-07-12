import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { ErrorAlert } from "./ErrorAlert";
it("renders a safe public error", () => { render(<ErrorAlert message="Fila indisponível" />); expect(screen.getByRole("alert")).toHaveTextContent("Fila indisponível"); expect(screen.queryByText(/traceback/i)).not.toBeInTheDocument(); });
