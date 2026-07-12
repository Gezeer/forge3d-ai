"use client";
import { useEffect, useState } from "react";
import { EngineSelector } from "@/components/generation/EngineSelector";
import { GenerateButton } from "@/components/generation/GenerateButton";
import { JobProgress } from "@/components/generation/JobProgress";
import { UploadDropzone } from "@/components/generation/UploadDropzone";
import { JobHistory } from "@/components/history/JobHistory";
import { Header } from "@/components/layout/Header";
import { Sidebar } from "@/components/layout/Sidebar";
import { ErrorAlert } from "@/components/ui/ErrorAlert";
import { ModelViewer } from "@/components/viewer/ModelViewer";
import { useJobPolling } from "@/hooks/useJobPolling";
import { HistoryJob, readHistory, saveHistory, upsertHistory } from "@/lib/history";
import { createGenerationJob, getDownloadUrl } from "@/services/api";
import { Engine, ForgeApiError, JobResponse } from "@/types/api";

export default function Home() {
  const [section, setSection] = useState("Criar 3D"); const [file, setFile] = useState<File | null>(null); const [engine, setEngine] = useState<Engine>("auto"); const [uploadError, setUploadError] = useState<string | null>(null); const [submitError, setSubmitError] = useState<ForgeApiError | null>(null); const [submitting, setSubmitting] = useState(false); const [history, setHistory] = useState<HistoryJob[]>([]); const { job, error: pollingError, start, setJob } = useJobPolling();
  useEffect(() => { const timer = window.setTimeout(() => setHistory(readHistory()), 0); return () => window.clearTimeout(timer); }, []);
  useEffect(() => { if (!job) return; const timer = window.setTimeout(() => setHistory((current) => saveHistory(upsertHistory({ jobId: job.job_id, engine: job.engine, status: job.status, createdAt: current.find((item) => item.jobId === job.job_id)?.createdAt || new Date().toISOString(), fileName: current.find((item) => item.jobId === job.job_id)?.fileName || file?.name || "imagem", downloadUrl: job.status === "completed" ? getDownloadUrl(job.job_id) : undefined }, current))), 0); return () => window.clearTimeout(timer); }, [job, file]);
  async function generate() { if (!file) return; setSubmitting(true); setSubmitError(null); try { const created = await createGenerationJob(file, engine); const initial: JobResponse = { job_id: created.job_id, engine: created.engine, status: "queued" }; setHistory((current) => saveHistory(upsertHistory({ jobId: created.job_id, engine: created.engine, status: "queued", createdAt: new Date().toISOString(), fileName: file.name }, current))); start(created.job_id, initial); } catch (cause) { setSubmitError(cause instanceof ForgeApiError ? cause : new ForgeApiError("Não foi possível criar o job.")); } finally { setSubmitting(false); } }
  function openHistory(item: HistoryJob) { setSection("Criar 3D"); setJob({ job_id: item.jobId, engine: item.engine, status: item.status, download_url: item.downloadUrl }); }
  function removeHistory(jobId: string) { setHistory((current) => saveHistory(current.filter((item) => item.jobId !== jobId))); }
  const activeError = uploadError || submitError?.message || pollingError?.message || (job?.status === "failed" ? job.error || "A geração falhou com segurança." : null); const modelUrl = job?.status === "completed" ? getDownloadUrl(job.job_id) : null;
  return <div className="app-shell"><Sidebar active={section} onNavigate={setSection} /><main><Header section={section} />{section === "Histórico" ? <div className="content history-page"><JobHistory jobs={history} onOpen={openHistory} onRemove={removeHistory} /></div> : <div className="content workspace"><section className="generation-card"><div className="section-title"><span>01</span><div><p>IMAGEM DE REFERÊNCIA</p><h2>Comece com uma boa imagem</h2></div></div><UploadDropzone file={file} onFile={setFile} onError={setUploadError} /><EngineSelector value={engine} onChange={setEngine} />{activeError && <ErrorAlert message={activeError} onRetry={file ? generate : undefined} />}<GenerateButton disabled={!file || Boolean(uploadError)} loading={submitting} onClick={generate} />{job && <JobProgress job={job} />}{job?.status === "completed" && <a className="download-button" href={getDownloadUrl(job.job_id)} download="forge3d-model.glb">↓ Baixar GLB</a>}</section><ModelViewer modelUrl={modelUrl} jobId={job?.job_id} /></div>}<footer><span>Forge3D AI</span><p>Geração 3D assistida por inteligência artificial.</p><span>Backend configurado por ambiente</span></footer></main></div>;
}
