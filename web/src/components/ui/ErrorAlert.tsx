export function ErrorAlert({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return <div role="alert" className="error-alert"><span>!</span><div><strong>Algo saiu do esperado</strong><p>{message}</p></div>{onRetry && <button onClick={onRetry}>Tentar novamente</button>}</div>;
}
