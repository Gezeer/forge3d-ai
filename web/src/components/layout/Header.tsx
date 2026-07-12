export function Header({ section }: { section: string }) {
  return <header className="topbar"><div><p>WORKSPACE / {section.toUpperCase()}</p><h1>{section === "Histórico" ? "Histórico de criações" : "Transforme imagem em 3D"}</h1></div><div className="topbar-actions"><span className="api-pill"><i />API conectada</span><span className="avatar">FA</span></div></header>;
}
