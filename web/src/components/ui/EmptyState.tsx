export function EmptyState({ title, description }: { title: string; description: string }) {
  return <div className="empty-state"><span className="empty-cube">◇</span><h3>{title}</h3><p>{description}</p></div>;
}
