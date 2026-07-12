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

O script testa a porta, lista endpoints, exige `/generation_all`, mostra ordem,
nome, tipo e default, oculta valores sensíveis e imprime o JSON pronto. Copie a
saída exata, por exemplo sintático:

```bash
export FORGE3D_HUNYUAN_SIGNATURE_JSON='{"args":[null,{"$image":"imageeditor"},30],"kwargs":{}}'
```

Esse exemplo não é a assinatura real. Use somente a saída do RunPod. Marcadores
aceitos: `simple`, `imagedata` e `imageeditor`. Defaults publicados permanecem
na ordem da API, sem parâmetros posicionais espalhados pelo serviço.

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
- **Artefato não encontrado:** confira a saída real de `/generation_all`. São
  aceitos GLB, OBJ, PLY e STL, como caminho, FileData ou URL HTTP temporária.
- **Falta de VRAM:** pare processos GPU concorrentes, reduza a concorrência da
  fila e use as configurações suportadas pelo Hunyuan. Não remova pesos/cache.
- **URL Gradio assinada:** ela é baixada para `outputs/{job_id}/`; nunca é
  devolvida ao cliente nem gravada nos metadados públicos.

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
