"use client";

import Image from "next/image";
import { ChangeEvent, DragEvent, useEffect, useMemo, useRef, useState } from "react";
import { formatBytes, validateUpload } from "@/lib/upload";

interface Props { file: File | null; onFile: (file: File | null) => void; onError: (message: string | null) => void; }

export function UploadDropzone({ file, onFile, onError }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const preview = useMemo(() => (file ? URL.createObjectURL(file) : ""), [file]);
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  function accept(next?: File) { if (!next) return; const error = validateUpload(next); onError(error); if (!error) onFile(next); }
  function change(event: ChangeEvent<HTMLInputElement>) { accept(event.target.files?.[0]); event.target.value = ""; }
  function drop(event: DragEvent) { event.preventDefault(); setDragging(false); accept(event.dataTransfer.files[0]); }

  return <div className={`dropzone ${dragging ? "dragging" : ""} ${file ? "has-file" : ""}`} onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={drop}>
    {file ? <><Image unoptimized width={92} height={92} src={preview} alt="Prévia da imagem selecionada" /><div className="file-info"><b>{file.name}</b><span>{formatBytes(file.size)} · {file.type.replace("image/", "").toUpperCase()}</span></div><div className="file-actions"><button onClick={() => input.current?.click()}>Trocar</button><button className="danger" onClick={() => { onFile(null); onError(null); }}>Remover</button></div></> : <button className="dropzone-empty" onClick={() => input.current?.click()}><span className="upload-icon">↥</span><b>Arraste sua imagem aqui</b><span>ou clique para selecionar</span><small>PNG, JPG ou WEBP · até 20 MB</small></button>}
    <input ref={input} type="file" accept="image/png,image/jpeg,image/webp" onChange={change} hidden />
  </div>;
}
