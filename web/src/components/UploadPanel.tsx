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
  const [jobId, setJobId] = useState("");

  async function handleGenerate() {
    if (!file) {
      setStatus("Selecione uma imagem primeiro.");
      return;
    }

    setLoading(true);
    setStatus("Enviando imagem e gerando modelo 3D...");
    setDownload("");
    setJobId("");
    onGenerated("");

    try {
      const result = await generateImage(file);

      console.log("Resultado da API:", result);

      if (result.status !== "success" || !result.glb_exists) {
        setStatus(
          `Erro ao gerar modelo.\n\n${resul

