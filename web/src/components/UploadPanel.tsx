"use client";

import { useState } from "react";
import { generateImage, downloadUrl } from "@/services/api";

interface UploadPanelProps {
  onGenerated: (modelUrl: string) => void;
}

export default function UploadPanel({ onGenerated }: UploadPanelProps) {
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState("Escolha uma imagem.");
  const [download, setDownload] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleGenerate() {
    if (!file) {
      setStatus("Selecione uma imagem.");
      return;
    }

    setLoading(true);
    setStatus("Gerando modelo 3D... aguarde.");
    setDownload("");

    try {
      const result = await generateImage(file);

      if (result.status !== "success") {
        setStatus("Erro ao gerar modelo.");
        console.log(result);
        return;
      }

      const url = downloadUrl(result.job_id);

      setStatus(`Modelo gerado com sucesso! Job: ${result.job_id}`);
      setDownload(url);
      onGenerated(url);
    } catch (err) {
      console.error(err);
      setStatus("Erro ao conectar com a API.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="rounded-2xl bg-slate-900 p-6 shadow-xl border border-slate-800">
      <h2 className="text-2xl font-bold text-white">Upload</h2>

      <p className="mt-2 text-sm text-slate-400">
        Envie uma imagem para gerar um modelo 3D em GLB.
      </p>

      <input
        type="file"
        accept="image/*"
        className="mt-6 w-full rounded-lg border border-slate-700 bg-slate-950 p-3 text-slate-300"
        onChange={(e) => setFile(e.target.files?.[0] || null)}
      />

      {file && (
        <p className="mt-3 text-sm text-emerald-300">
          Imagem: {file.name}
        </p>
      )}

      <button
        onClick={handleGenerate}
        disabled={loading}
        className="mt-6 w-full rounded-xl bg-emerald-400 p-4 font-bold text-black hover:bg-emerald-300 disabled:opacity-50"
      >
        {loading ? "Gerando..." : "Gerar Modelo 3D"}
      </button>

      <div className="mt-6 rounded-xl bg-slate-950 p-4 text-sm text-yellow-300 whitespace-pre-wrap">
        {status}
      </div>

      {download && (
        <a
          href={download}
          download
          className="mt-6 block rounded-xl bg-slate-800 p-4 text-center font-bold text-emerald-300 hover:bg-slate-700"
        >
          Baixar GLB
        </a>
      )}
    </div>
  );
}
