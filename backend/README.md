# Forge3D AI backend

Backend FastAPI modular para geração 3D. O TripoSR preserva o contrato legado
do RunPod e o Hunyuan fica isolado atrás de um gateway Gradio configurável.

## Garantias desta fase

- Nenhum modelo é carregado durante import da aplicação.
- O TripoSR continua usando `cuda:0`, pedindo GLB e procurando
  `<job>/0/mesh.glb`.
- `/generate/image`, `/download/{job_id}` e `/health` permanecem compatíveis.
- Jobs usam os estados `queued`, `processing`, `completed` e `failed`.
- O repositório JSON implementa uma interface substituível futuramente por
  PostgreSQL.
- O Hunyuan não presume a assinatura da UI Gradio.
- Engines implementam um contrato comum e são resolvidas por `EngineRegistry`.
- A fila local implementa `JobQueue`, que pode ganhar outro adaptador no futuro.
- Workers locais só são iniciados e encerrados pelo lifespan do FastAPI.

## Desenvolvimento local sem modelos

Requer Python 3.9 ou superior. O ambiente local instala apenas API e testes:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
backend/scripts/start_local.sh
```

Os diretórios locais são gravados em `.runtime/`. Gerar com TripoSR ou Hunyuan
localmente não é esperado; os testes usam injeção e mocks.

## RunPod

O diagnóstico do proxy, as portas públicas e a inicialização conjunta com o
Next.js estão em [`backend/docs/RUNPOD_DEPLOYMENT.md`](docs/RUNPOD_DEPLOYMENT.md).

No RunPod, instale a API e o extra leve do cliente Hunyuan, sem reinstalar nem
alterar os modelos existentes:

```bash
python3 -m pip install -e '.[hunyuan]'
backend/scripts/start_runpod.sh
```

Todos os caminhos podem ser sobrescritos pelas variáveis documentadas em
`.env.example`. Os valores padrão mantêm os caminhos atuais do RunPod.

## Validação real no RunPod: quatro terminais

Defina primeiro uma imagem pequena e os caminhos já existentes, sem instalar ou
alterar modelos.

### Terminal 1 — iniciar Hunyuan na porta 8080

O comando de inicialização varia conforme o checkout real do Hunyuan. Informe o
comando já validado nesse ambiente:

```bash
cd /workspace/forge3d-ai
export HUNYUAN_ROOT=/workspace/kai3d/models/Hunyuan3D-2.1
export HUNYUAN_PORT=8080
export HUNYUAN_START_COMMAND='<comando real do Hunyuan que publica a porta 8080>'
backend/scripts/start_hunyuan.sh
```

O script falha se o diretório ou comando estiver ausente e não instala nada.

### Terminal 2 — inspecionar a assinatura publicada

```bash
cd /workspace/forge3d-ai
PYTHONPATH=backend python3 backend/scripts/inspect_hunyuan_api.py
```

O script testa a porta, lista endpoints, exige `/shape_generation`, mostra ordem,
nome, tipo e default, oculta valores sensíveis e imprime o JSON pronto. Copie a
saída exata, por exemplo sintático:

```bash
export FORGE3D_HUNYUAN_API_NAME=/shape_generation
export FORGE3D_HUNYUAN_SIGNATURE_JSON='{"args":[{"$image":"simple"},null,null,null,null,30,5.0,1234,256,true,8000,false],"kwargs":{}}'
```

Essa assinatura foi confirmada no RunPod para `/shape_generation`. Somente o
primeiro argumento recebe a imagem; os quatro campos multiview permanecem
`null`. Marcadores aceitos pelo gateway continuam sendo `simple`, `imagedata` e
`imageeditor` para compatibilidade com outras APIs publicadas.

### Terminal 3 — iniciar Forge3D na porta 8000

```bash
cd /workspace/forge3d-ai
export FORGE3D_HUNYUAN_URL=http://127.0.0.1:8080
export FORGE3D_OUTPUT_DIR=/workspace/forge3d-ai/outputs
export PORT=8000
backend/scripts/start_forge3d.sh
```

Verifique portas e PIDs:

```bash
backend/scripts/check_services.sh
```

### Terminal 4 — executar testes GPU reais

```bash
cd /workspace/forge3d-ai
export FORGE3D_TEST_API_URL=http://127.0.0.1:8000
export FORGE3D_TEST_IMAGE=/workspace/forge3d-ai/test-image.png
export FORGE3D_GPU_TEST_TIMEOUT=1200
backend/scripts/test_gpu.sh
```

Os testes exigem Hunyuan disponível no health, geração Hunyuan síncrona e em
fila, polling até conclusão, artefato físico não vazio, extensão 3D reconhecida
e download. Também confirmam a rota legada TripoSR, GLB e `0/mesh.glb`.

## Troubleshooting Hunyuan/RunPod

- **Porta 8080 indisponível:** execute `check_services.sh`, confira o PID e o
  log do Terminal 1. O inspetor retorna exit code diferente de zero.
- **Erro ImageData/ImageEditor:** execute novamente o inspetor e use exatamente
  o marcador gerado. `ImageEditor` envia `background`, `layers` e `composite`.
- **Timeout:** aumente `FORGE3D_GENERATION_TIMEOUT_SECONDS` e
  `FORGE3D_GPU_TEST_TIMEOUT`, verificando antes se o processo ainda usa GPU.
- **Artefato não encontrado:** confira a saída real de `/shape_generation`. São
  aceitos GLB, OBJ, PLY e STL, como caminho, FileData ou URL HTTP temporária.
- **Falta de VRAM:** pare processos GPU concorrentes, reduza a concorrência da
  fila e use as configurações suportadas pelo Hunyuan. Não remova pesos/cache.
- **URL Gradio assinada:** ela é baixada para `outputs/{job_id}/`; nunca é
  devolvida ao cliente nem gravada nos metadados públicos.

## Hunyuan Texture/PBR

A textura é um estágio separado e nunca invalida `model.glb`. O endpoint
`POST /jobs/{job_id}/texture` enfileira o paint; o resultado esperado é
`outputs/{job_id}/model_textured.glb`. Consulte o estágio em
`GET /jobs/{job_id}/texture` e baixe por `GET /download/{job_id}/textured`.

O checkout local não contém `hy3dpaint/textureGenPipeline.py`, `gradio_app.py`,
pesos ou requisitos Hunyuan. No RunPod, diagnostique o ambiente real antes de
definir o comando:

O pipeline automático de produção e a API `/api/v1/texture` estão documentados
em [`backend/docs/TEXTURE_PIPELINE.md`](docs/TEXTURE_PIPELINE.md).

```bash
cd /workspace/forge3d-ai
backend/scripts/check_texture_dependencies.sh
PYTHONPATH=backend python3 backend/scripts/inspect_hunyuan_texture.py
```

O diagnóstico verifica `bpy`, `pymeshlab`, `libOpenGL.so.0`, CUDA/VRAM, imports
do pipeline, pesos e caches. Ele não instala nada. Dependências já confirmadas
como problemáticas no RunPod são Blender Python (`bpy`) e a biblioteca do
sistema `libOpenGL.so.0`; `pymeshlab` e o `DifferentiableRenderer` também devem
ser importáveis no mesmo ambiente que executa o paint.

### Compilar o mesh inpaint oficial

O `mesh_inpaint_processor` é uma extensão C++/pybind11 do Hunyuan Paint. Ela
deve ser compilada com o mesmo interpretador que executa o pipeline; misturar o
`python` do ambiente virtual com o `python3-config` do sistema pode gerar um
arquivo com ABI incompatível.

```bash
cd /workspace/forge3d-ai
export HUNYUAN_ROOT=/workspace/kai3d/models/Hunyuan3D-2.1
export HUNYUAN_PYTHON=/workspace/kai3d/models/Hunyuan3D-2.1/venv/bin/python
backend/scripts/compile_hunyuan_mesh_inpaint.sh
```

O script não instala dependências. Ele usa o interpretador indicado tanto nos
includes do pybind11 quanto no sufixo ABI, compila o módulo no diretório oficial
e executa o teste de importação. Para também chamar a função com uma entrada
NumPy mínima:

```bash
PYTHONPATH="$HUNYUAN_ROOT" "$HUNYUAN_PYTHON" \
  backend/scripts/test_hunyuan_mesh_inpaint.py \
  --root "$HUNYUAN_ROOT" --functional
```

O patch opcional `backend/patches/hunyuan_meshrender_mesh_inpaint.patch` faz o
`MeshRender.py` preservar a causa original do `ImportError`, em vez de continuar
sem definir `meshVerticeInpaint` e falhar depois com `NameError`:

```bash
cd "$HUNYUAN_ROOT"
git apply /workspace/forge3d-ai/backend/patches/hunyuan_meshrender_mesh_inpaint.patch
```

Configure o pipeline automático validado:

```bash
export FORGE3D_ROOT=/workspace/forge3d-ai
export FORGE3D_TEXTURE_ROOT=/workspace/kai3d/models/Hunyuan3D-2.1
export FORGE3D_TEXTURE_PYTHON=/workspace/kai3d/models/Hunyuan3D-2.1/venv/bin/python
export FORGE3D_BLENDER_EXECUTABLE=blender
export FORGE3D_TEXTURE_TIMEOUT_SECONDS=1800
```

O serviço chama os dois scripts Blender em background e usa exclusivamente
`backend/scripts/run_hunyuan_paint.py` para o Paint. Para validar GPU com um job
de shape já concluído:

```bash
export FORGE3D_TEXTURE_TEST_JOB_ID=<uuid-completed>
export FORGE3D_TEST_API_URL=http://127.0.0.1:8000
backend/scripts/test_texture_gpu.sh
```

## Endpoints

- `POST /generate/image` — alias temporário do TripoSR.
- `POST /generate/triposr` — TripoSR explícito.
- `POST /generate/hunyuan` — Hunyuan explícito.
- `POST /generate/auto` — seleção pela política automática isolada.
- `POST /jobs/generate` — enfileira geração e responde imediatamente com HTTP 202.
- `GET /download/{job_id}` — download do artefato concluído.
- `GET /jobs/{job_id}` — estado e metadados do job.
- `GET /health` — saúde da API e configuração local.

As gerações ainda são síncronas nesta fase: o estado é persistido, mas a
resposta dos endpoints legados chega quando o gerador termina. O endpoint
`/jobs/generate` usa a fila local e responde antes da geração terminar.

O formulário do novo endpoint recebe `file` e `engine`, que pode ser `auto`,
`triposr` ou `hunyuan`. A política `auto` prefere Hunyuan quando ele está
configurado e disponível, usando `FORGE3D_AUTO_ENGINE_FALLBACK` como fallback.
`FORGE3D_DEFAULT_ENGINE` é usado quando o campo `engine` não é enviado.

A concorrência e capacidade da fila são controladas por
`FORGE3D_QUEUE_CONCURRENCY` e `FORGE3D_QUEUE_MAX_SIZE`. A fila é somente em
memória: jobs que ainda não começaram não são retomados automaticamente após
reinício do processo.

## Observabilidade

Use `FORGE3D_LOG_LEVEL` para controlar o nível e `FORGE3D_LOG_FORMAT=text` em
desenvolvimento. Em produção, `FORGE3D_LOG_FORMAT=json` gera um objeto JSON por
linha com campos seguros como `request_id`, `job_id`, engine, status, duração e
código de erro. Imagens, tokens, segredos e stderr integral não são registrados.

Toda resposta inclui `X-Request-ID`. Um UUID válido enviado nesse header é
preservado; caso contrário, a API gera um novo.

- `/health/live` confirma somente que o processo responde e não consulta engines.
- `/health/ready` confirma storage, repositório, fila e ao menos uma engine.
- `/health` apresenta o diagnóstico detalhado, preservando os campos legados.

Probes usam `FORGE3D_HEALTH_TIMEOUT_SECONDS`. Hunyuan desligado deixa a saúde
geral como `degraded` quando o TripoSR está disponível.

`GET /metrics` expõe o formato Prometheus no mesmo servidor. Pode ser desligado
com `FORGE3D_METRICS_ENABLED=false`. Labels nunca incluem filename, job ID ou
request ID.

## Validações do CI

O GitHub Actions usa Python 3.9 e 3.12 e não baixa modelos. Execute localmente:

```bash
PYTHONPATH=backend .venv/bin/python -m ruff check backend
PYTHONPATH=backend .venv/bin/python -m ruff format --check backend
PYTHONPATH=backend .venv/bin/python -m pytest -m 'not gpu'
PYTHONPYCACHEPREFIX=/tmp/forge3d-pycache \
  .venv/bin/python -m py_compile $(find backend -name '*.py' -type f)
git diff --check
bash -n backend/scripts/start_local.sh backend/scripts/start_runpod.sh
```

## Testes

```bash
PYTHONPATH=backend .venv/bin/python -m pytest
PYTHONPYCACHEPREFIX=/tmp/forge3d-pycache \
  .venv/bin/python -m py_compile $(find backend -name '*.py' -type f)
```

Testes GPU ficam ignorados por padrão. Para executá-los deliberadamente no
RunPod, configure `RUN_GPU_TESTS=1`, `FORGE3D_TEST_API_URL` e
`FORGE3D_TEST_IMAGE`.
