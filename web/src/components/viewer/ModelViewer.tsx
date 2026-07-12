"use client";

import { Component, ReactNode, Suspense, useRef, useState } from "react";
import { Bounds, Center, Grid, Html, OrbitControls, useGLTF } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { EmptyState } from "@/components/ui/EmptyState";
import { LoadingState } from "@/components/ui/LoadingState";

class ViewerErrorBoundary extends Component<
  { children: ReactNode; resetKey: number },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidUpdate(previous: { resetKey: number }) {
    if (previous.resetKey !== this.props.resetKey && this.state.failed) this.setState({ failed: false });
  }
  render() {
    return this.state.failed ? <div className="viewer-message"><b>Não foi possível abrir este GLB.</b><span>O download continua disponível.</span></div> : this.props.children;
  }
}

function Model({ url }: { url: string }) {
  const gltf = useGLTF(url);
  return <primitive object={gltf.scene.clone()} />;
}

export function ModelViewer({ modelUrl, jobId }: { modelUrl: string | null; jobId?: string }) {
  const shell = useRef<HTMLDivElement>(null);
  const [grid, setGrid] = useState(true);
  const [reset, setReset] = useState(0);
  async function fullscreen() {
    if (!document.fullscreenElement) await shell.current?.requestFullscreen();
    else await document.exitFullscreen();
  }
  return <section className="viewer-card">
    <div className="viewer-head"><div><span>PREVIEW 3D</span><h2>{jobId ? `Modelo ${jobId.slice(0, 8)}` : "Seu modelo aparecerá aqui"}</h2></div><div className="viewer-tools"><button disabled={!modelUrl} onClick={() => setReset((value) => value + 1)} title="Centralizar modelo">⌖</button><button disabled={!modelUrl} className={grid ? "active" : ""} onClick={() => setGrid((value) => !value)} title="Alternar grid">▦</button><button disabled={!modelUrl} onClick={fullscreen} title="Tela cheia">⛶</button></div></div>
    <div ref={shell} className="viewer-shell">{modelUrl ? <ViewerErrorBoundary resetKey={reset}><Canvas key={reset} camera={{ position: [2.8, 2.2, 3.8], fov: 42 }} dpr={[1, 2]}><color attach="background" args={["#09101b"]} /><ambientLight intensity={1.2} /><directionalLight position={[4, 6, 4]} intensity={2.5} /><Suspense fallback={<Html center><LoadingState label="Carregando modelo" /></Html>}><Bounds fit clip observe margin={1.25}><Center><Model url={modelUrl} /></Center></Bounds></Suspense>{grid && <Grid position={[0, -1, 0]} infiniteGrid fadeDistance={24} sectionColor="#31566d" cellColor="#193342" />}<OrbitControls makeDefault enablePan enableZoom /></Canvas></ViewerErrorBoundary> : <EmptyState title="Preview tridimensional" description="Envie uma imagem e acompanhe a criação da malha em tempo real." />}<span className="viewer-hint">Arraste para rotacionar · Scroll para zoom · Botão direito para mover</span></div>
  </section>;
}
