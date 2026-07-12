import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Forge3D AI — Image to 3D Studio",
  description: "Workspace profissional para transformar imagens em modelos 3D.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="pt-BR"><body>{children}</body></html>;
}
