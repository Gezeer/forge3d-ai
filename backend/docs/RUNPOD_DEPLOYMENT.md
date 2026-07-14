# Forge3D no proxy HTTP do RunPod

## Diagnóstico do 502

O FastAPI já responde em `127.0.0.1:8000`, no IP da interface do Pod e escuta
em `0.0.0.0:8000`. Além disso, nenhuma requisição do domínio público aparece no
access log. Portanto, o 502 é produzido antes do Uvicorn, no mapeamento HTTP do
Pod. CORS e middleware só podem atuar depois que a requisição chega à aplicação.

No painel RunPod, configure exatamente estes HTTP ports:

```text
3000
8000
8888
```

Não configure 3000 ou 8000 somente como TCP. Depois de salvar a configuração,
reinicie o Pod para recriar o registro do proxy. O formato público é:

```text
https://POD_ID-3000.proxy.runpod.net
https://POD_ID-8000.proxy.runpod.net
```

O proxy RunPod termina HTTPS e encaminha HTTP ao Pod. Uvicorn não deve carregar
certificados TLS próprios.

## Inicialização

O Node.js 22 e as dependências Python devem estar instalados previamente.

```bash
cd /workspace/forge3d-ai
export FORGE3D_ROOT=/workspace/forge3d-ai
export FORGE3D_HUNYUAN_URL=http://127.0.0.1:8080
export FORGE3D_INTERNAL_API_URL=http://127.0.0.1:8000
./start.sh
```

`start.sh` inicia o backend, espera `/health/live` e só então inicia o build
Next.js em `0.0.0.0:3000`. O navegador usa `/forge3d-api`; a chamada é
encaminhada pelo servidor Next para `127.0.0.1:8000`. Assim, o navegador nunca
tenta acessar o próprio localhost e o fluxo normal não depende de CORS.

## Verificação do proxy

```bash
cd /workspace/forge3d-ai
export RUNPOD_POD_ID=<id-real-do-pod>
backend/scripts/diagnose_runpod_proxy.sh
```

Exit code 3 significa que a aplicação respondeu internamente, mas o mapeamento
RunPod não alcançou a porta. Nesse caso não existe alteração FastAPI capaz de
corrigir o salto externo: revise `8000/http`, salve e reinicie o Pod.

Após iniciar:

```bash
curl --fail http://127.0.0.1:8000/
curl --fail http://127.0.0.1:8000/health/live
curl --fail "https://${RUNPOD_POD_ID}-8000.proxy.runpod.net/"
curl --fail "https://${RUNPOD_POD_ID}-3000.proxy.runpod.net/"
```

## Hunyuan indisponível no health

Uma resposta HTML em `127.0.0.1:8080/` prova apenas que existe um servidor HTTP.
O Forge3D exige `/gradio_api/openapi.json` com o endpoint lógico
`POST /run/shape_generation`. O prefixo HTTP vem de `/config`, com
`/gradio_api` como fallback; a execução normalmente usa
`POST /gradio_api/run/shape_generation`. O health apenas valida o contrato e não
executa geração.

Embora o OpenAPI publique 12 parâmetros, o handler real recebe 13 entradas: um
`State` oculto (`null`) no índice zero e, depois, os 12 valores na ordem do
schema. O cliente detecta esse componente em `/config`, evita duplicá-lo e usa
um único `null` inicial como fallback específico para `shape_generation`.

```bash
curl -s http://127.0.0.1:8000/health | python3 -m json.tool
PYTHONPATH=backend python3 backend/scripts/inspect_hunyuan_api.py
```

O backend usa HTTP/OpenAPI diretamente e não depende de `gradio_client`.
`ConnectError` indica que o servidor ainda não aceita conexões; respostas 425,
429, 502, 503 e 504 são tratadas como inicialização e recebem retry exponencial.

## Shape Hunyuan com textura automática

Depois que um job Hunyuan termina o shape, o mesmo worker enfileira o pipeline
Blender → Hunyuan Paint → Blender. O GLB branco continua em
`outputs/<job_id>/model.glb`; os arquivos intermediários ficam isolados em
`outputs/<job_id>/texture_work`; o resultado final é
`outputs/<job_id>/model_textured.glb`.

O acesso à GPU é serializado por `FORGE3D_GPU_LOCK_PATH`. Depois do shape, o
worker envia SIGTERM somente ao processo cujo Python, `gradio_app.py`, porta e
diretório de trabalho correspondem à configuração. SIGKILL só é usado após
`FORGE3D_HUNYUAN_STOP_TIMEOUT_SECONDS`. FastAPI, Blender e outros processos
Python nunca são alvos.

```bash
export FORGE3D_TEXTURE_ROOT=/workspace/kai3d/models/Hunyuan3D-2.1
export FORGE3D_TEXTURE_PYTHON=/workspace/kai3d/models/Hunyuan3D-2.1/venv/bin/python
export FORGE3D_BLENDER_EXECUTABLE=/usr/bin/blender
export FORGE3D_TEXTURE_CACHE=/workspace/.cache/forge3d-texture
export TMPDIR=/tmp
export FORGE3D_TEXTURE_TIMEOUT_SECONDS=1800
export FORGE3D_HUNYUAN_ROOT=/workspace/kai3d/models/Hunyuan3D-2.1
export FORGE3D_HUNYUAN_PYTHON=/workspace/kai3d/models/Hunyuan3D-2.1/venv/bin/python
export FORGE3D_HUNYUAN_PORT=8080
export FORGE3D_HUNYUAN_CACHE_PATH=/tmp/hunyuan-cache
export FORGE3D_HUNYUAN_LOG=/tmp/hunyuan-shape.log
export FORGE3D_GPU_LOCK_PATH=/tmp/forge3d-gpu.lock
python3 backend/scripts/test_texture_e2e.py \
  --image /workspace/forge3d-ai/examples/robot.png
```

O teste espera `texture_status=completed`, baixa o GLB branco e o texturizado,
valida o cabeçalho GLB, executa `file` e rejeita artefatos vazios. Se Blender ou
Paint falhar, o shape permanece `completed`, o download original continua ativo
e a textura termina com `texture_status=failed` e erro resumido.

Teste completo do ciclo de VRAM:

```bash
python3 backend/scripts/test_full_hunyuan_pipeline.py \
  --image /workspace/forge3d-ai/examples/robot.png
```

O script exige observar a porta 8080 fechada em `texturing`, novamente aberta
ao final, health Hunyuan saudável e os dois GLBs 2.0 válidos.

O Paint nunca usa `/root/.cache` nem `~/.cache`. Antes de importar as bibliotecas
de ML, o wrapper direciona todos os caches HuggingFace, Transformers, Diffusers
e Torch para subdiretórios de `FORGE3D_TEXTURE_CACHE`, configura `tempfile` com
`TMPDIR` e desativa Xet. Downloads HTTP parciais permanecem no cache para
retomada automática nos retries exponenciais.

```bash
mkdir -p /workspace/.cache/forge3d-texture/{cache,hub,transformers,datasets,torch}
PYTHONPATH=backend python3 backend/scripts/inspect_hunyuan_texture.py
```

## Endpoints usados pelo frontend

- `POST /api/v1/generate`: cria um job assíncrono;
- `GET /jobs/{job_id}`: polling;
- `GET /download/{job_id}`: GLB original;
- `POST /api/v1/texture`: pipeline de textura;
- `GET /download/{job_id}/textured`: GLB texturizado.

As operações GPU continuam fora da requisição HTTP. Isso respeita o limite de
conexão do proxy e evita manter uploads bloqueados durante a inferência.
