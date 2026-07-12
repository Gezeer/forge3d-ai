import { EmptyState } from "@/components/ui/EmptyState";
import { HistoryJob } from "@/lib/history";
export function JobHistory({ jobs, onOpen, onRemove }: { jobs: HistoryJob[]; onOpen: (job: HistoryJob) => void; onRemove: (jobId: string) => void }) {
  if (!jobs.length) return <div className="history-card"><EmptyState title="Nenhuma criação ainda" description="Seus jobs recentes ficarão salvos neste dispositivo." /></div>;
  return <div className="history-card"><div className="history-head"><span>MODELOS RECENTES</span><b>{jobs.length} {jobs.length === 1 ? "job" : "jobs"}</b></div><div className="history-list">{jobs.map((job) => <article key={job.jobId}><span className={`history-status ${job.status}`} /> <div><b>{job.fileName}</b><small>{new Date(job.createdAt).toLocaleString("pt-BR")} · {job.engine}</small><code>{job.jobId}</code></div><em>{job.status}</em><div className="history-actions"><button disabled={job.status !== "completed"} onClick={() => onOpen(job)}>Abrir</button>{job.downloadUrl && <a href={job.downloadUrl} download>Baixar</a>}<button className="danger" onClick={() => onRemove(job.jobId)}>Remover</button></div></article>)}</div></div>;
}
