export function GenerateButton({ disabled, loading, onClick }: { disabled: boolean; loading: boolean; onClick: () => void }) {
  return <button className="generate-button" disabled={disabled || loading} onClick={onClick}>{loading ? <><span className="spinner" />Enfileirando...</> : <><span>✦</span>Gerar modelo 3D</>}</button>;
}
