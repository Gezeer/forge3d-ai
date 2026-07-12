import { JobResponse } from "@/types/api";
const steps = ["queued", "processing", "completed"];
export function JobProgress({ job }: { job: JobResponse }) {
  const active = job.status === "failed" ? 1 : Math.max(0, steps.indexOf(job.status));
  return <section className="job-progress" aria-live="polite"><div className="job-meta"><span>JOB</span><code>{job.job_id}</code><b>{job.engine}</b></div><div className="progress-line">{steps.map((step, index) => <div key={step} className={index <= active ? "done" : ""}><i>{index < active ? "✓" : index + 1}</i><span>{step === "queued" ? "Na fila" : step === "processing" ? "Gerando geometria" : "Modelo pronto"}</span></div>)}</div><p>{job.status === "queued" ? "Seu job entrou na fila de processamento." : job.status === "processing" ? "A GPU está construindo sua malha 3D." : job.status === "completed" ? "Modelo concluído e pronto para visualizar." : "A geração não pôde ser concluída."}</p></section>;
}
