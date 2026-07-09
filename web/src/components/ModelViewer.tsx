"use client";

import { Canvas } from "@react-three/fiber";
import { OrbitControls, Stage, useGLTF } from "@react-three/drei";

function Model({ url }: { url: string }) {
  const gltf = useGLTF(url);
  return <primitive object={gltf.scene} />;
}

export default function ModelViewer({ modelUrl }: { modelUrl: string }) {
  return (
    <div className="h-[650px] rounded-2xl overflow-hidden bg-slate-900 border border-slate-800">
      {modelUrl ? (
        <Canvas camera={{ position: [2, 2, 4], fov: 45 }}>
          <ambientLight intensity={1.5} />
          <Stage environment="city" intensity={1}>
            <Model url={modelUrl} />
          </Stage>
          <OrbitControls />
        </Canvas>
      ) : (
        <div className="flex h-full items-center justify-center text-center text-slate-400">
          <div>
            <div className="text-7xl">🧊</div>
            <h2 className="mt-4 text-2xl font-bold text-white">
              Preview 3D
            </h2>
            <p className="mt-2">O modelo gerado aparecerá aqui.</p>
          </div>
        </div>
      )}
    </div>
  );
}
