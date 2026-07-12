import { Engine } from "@/types/api";
const engines: { value: Engine; label: string; description: string; tag?: string }[] = [
  { value: "auto", label: "Auto", description: "Escolhe a engine disponível", tag: "RECOMENDADO" },
  { value: "triposr", label: "TripoSR", description: "Geração mais rápida" },
  { value: "hunyuan", label: "Hunyuan", description: "Melhor qualidade geométrica" },
];
export function EngineSelector({ value, onChange }: { value: Engine; onChange: (engine: Engine) => void }) {
  return <fieldset className="engine-selector"><legend>Engine de geração</legend>{engines.map((engine) => <label key={engine.value} className={value === engine.value ? "selected" : ""}><input type="radio" name="engine" value={engine.value} checked={value === engine.value} onChange={() => onChange(engine.value)} /><span className="radio-dot" /><span><b>{engine.label}</b><small>{engine.description}</small></span>{engine.tag && <em>{engine.tag}</em>}</label>)}</fieldset>;
}
