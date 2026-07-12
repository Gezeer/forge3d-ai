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

## Descobrir a assinatura real do Hunyuan

Com a UI Gradio ativa na porta 8080:

```bash
PYTHONPATH=backend python3 backend/scripts/inspect_hunyuan_api.py \
  --url http://127.0.0.1:8080
```

Converta a assinatura exibida para JSON, sem mudar a ordem dos argumentos. O
marcador `{"$image": true}` indica onde o gateway deve inserir o upload:

```bash
export FORGE3D_HUNYUAN_SIGNATURE_JSON='{"args":[null,{"$image":true}],"kwargs":{}}'
```

O exemplo acima é apenas a sintaxe da configuração, não a assinatura real. A
integração Hunyuan só pode ser validada após inspeção e geração real no RunPod.

## Endpoints

- `POST /generate/image` — alias temporário do TripoSR.
- `POST /generate/triposr` — TripoSR explícito.
- `POST /generate/hunyuan` — Hunyuan explícito.
- `POST /generate/auto` — motor definido por `FORGE3D_AUTO_ENGINE`.
- `GET /download/{job_id}` — download do artefato concluído.
- `GET /jobs/{job_id}` — estado e metadados do job.
- `GET /health` — saúde da API e configuração local.

As gerações ainda são síncronas nesta fase: o estado é persistido, mas a
resposta do POST chega quando o gerador termina. Uma fila externa pode ser
adicionada depois sem mudar o contrato do repositório de jobs.

## Testes

```bash
PYTHONPATH=backend .venv/bin/python -m pytest
PYTHONPYCACHEPREFIX=/tmp/forge3d-pycache \
  .venv/bin/python -m py_compile $(find backend -name '*.py' -type f)
```

Testes GPU ficam ignorados por padrão. Para executá-los deliberadamente no
RunPod, configure `RUN_GPU_TESTS=1`, `FORGE3D_TEST_API_URL` e
`FORGE3D_TEST_IMAGE`.
