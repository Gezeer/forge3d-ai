#!/bin/bash

echo "🚀 Iniciando Forge3D AI..."

echo "📡 Iniciando API FastAPI na porta 8000..."
cd /workspace/forge3d-ai/backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
API_PID=$!

echo "🌐 Iniciando Frontend na porta 3000..."
cd /workspace/forge3d-ai/frontend
python3 -m http.server 3000 &
FRONTEND_PID=$!

echo ""
echo "✅ Forge3D AI iniciado!"
echo "API: http://127.0.0.1:8000"
echo "Frontend: http://127.0.0.1:3000"
echo ""
echo "Pressione CTRL+C para parar tudo."

wait
