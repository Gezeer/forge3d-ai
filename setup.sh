#!/bin/bash
set -e

echo "🚀 Configurando Forge3D AI..."

echo "📦 Atualizando sistema..."
apt update

echo "🟢 Instalando curl..."
apt install -y curl ca-certificates gnupg

echo "🐍 Instalando dependências Python..."
python3 -m pip install --upgrade pip
python3 -m pip install fastapi uvicorn python-multipart

echo "🟩 Instalando Node.js..."
if ! command -v node >/dev/null 2>&1; then
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  apt install -y nodejs
fi

echo "📌 Versões:"
python3 --version
node -v
npm -v

echo "🌐 Instalando dependências do frontend..."
cd /workspace/forge3d-ai/web
npm install

echo "✅ Setup concluído!"
echo ""
echo "Para iniciar:"
echo "Backend:"
echo "cd /workspace/forge3d-ai/backend && python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"
echo ""
echo "Frontend:"
echo "cd /workspace/forge3d-ai/web && npm run dev"
