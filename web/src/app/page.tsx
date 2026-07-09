"use client";

import { useState } from "react";
import Header from "@/components/Header";
import UploadPanel from "@/components/UploadPanel";
import ModelViewer from "@/components/ModelViewer";

export default function Home() {
  const [modelUrl, setModelUrl] = useState("");

  return (
    <main className="min-h-screen bg-slate-950">
      <Header />

      <div className="mx-auto max-w-7xl grid grid-cols-1 lg:grid-cols-2 gap-8 p-8">
        <UploadPanel onGenerated={setModelUrl} />
        <ModelViewer modelUrl={modelUrl} />
      </div>
    </main>
  );
}
