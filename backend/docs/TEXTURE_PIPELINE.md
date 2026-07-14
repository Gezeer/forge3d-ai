# Pipeline automático de textura Hunyuan

O Forge3D executa a cadeia validada no RunPod sem comandos manuais:

```text
outputs/<job_id>/model.glb
  -> Blender headless
outputs/<job_id>/texture_work/white_mesh.obj
  -> Hunyuan Paint
outputs/<job_id>/texture_work/textured_mesh.obj
  -> Blender headless
outputs/<job_id>/model_textured.glb
```

O modelo branco permanece disponível mesmo quando alguma etapa de textura
falha. O resultado final é persistido no job como `output_textured_glb` e pode
ser baixado por `GET /download/{job_id}/textured`.

## Configuração RunPod

```bash
export FORGE3D_ROOT=/workspace/forge3d-ai
export FORGE3D_TEXTURE_ROOT=/workspace/kai3d/models/Hunyuan3D-2.1
export FORGE3D_TEXTURE_PYTHON=/workspace/kai3d/models/Hunyuan3D-2.1/venv/bin/python
export FORGE3D_BLENDER_EXECUTABLE=/usr/bin/blender
export FORGE3D_TEXTURE_CACHE=/workspace/.cache/forge3d-texture
export TMPDIR=/tmp
export FORGE3D_TEXTURE_TIMEOUT_SECONDS=1800
```

Na primeira execução, o wrapper cria os caches dedicados, confirma escrita e
espaço livre e carrega o modelo. O HuggingFace reutiliza blobs completos e
retoma arquivos `.incomplete` após falhas de rede. Xet fica desativado para que
nenhuma escrita volte ao cache padrão do usuário ou ao downloader nativo que
produziu o segfault após o erro de quota.

O backend não instala Blender, modelos ou dependências. O comando configurado em
`FORGE3D_TEXTURE_PYTHON` precisa ser o mesmo ambiente no qual o Hunyuan Paint,
`custom_rasterizer` e `mesh_inpaint_processor` foram validados.

## Execução automática

Todo job criado com `engine=hunyuan` inicia automaticamente a textura depois
que o shape chega a `completed`. A criação continua respondendo HTTP 202 sem
esperar Blender ou Paint. O job mantém o shape em `completed` e evolui
`texture_status` de `null` para `texturing` e então `completed` ou `failed`.

Os parâmetros automáticos são `resolution=512` e `quality=fast`.

Antes do pipeline, Shape e Paint são serializados por um lock de arquivo
interprocesso. O `gradio_app.py --port 8080` é encerrado com SIGTERM, a saída do
processo e a liberação da porta são confirmadas e a VRAM é registrada por
`nvidia-smi` quando disponível. Em `finally`, o Shape é iniciado em nova sessão,
com logs redirecionados, e o worker aguarda o OpenAPI voltar. O lock só é
liberado depois dessa confirmação.

Durante esse intervalo, o health usa os estados operacionais
`paused_for_texture` e `restarting`, sem transformar a pausa controlada em falha
global da API.

## API manual compatível

O job de geometria precisa estar no estado `completed` e possuir `model.glb`.

```bash
curl -X POST http://127.0.0.1:8000/api/v1/texture \
  -F job_id=<uuid-do-job> \
  -F engine=hunyuan \
  -F resolution=512 \
  -F quality=fast
```

Uma nova imagem de referência é opcional:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/texture \
  -F job_id=<uuid-do-job> \
  -F file=@examples/robot.png \
  -F engine=hunyuan \
  -F resolution=512 \
  -F quality=fast
```

A API responde HTTP 202. Consulte `GET /jobs/{job_id}` ou
`GET /jobs/{job_id}/texture`. Ao concluir, use:

```bash
curl -o model_textured.glb \
  http://127.0.0.1:8000/download/<job_id>/textured
```

As rotas anteriores `POST /jobs/{job_id}/texture` e os downloads do GLB branco
continuam disponíveis.

## Artefatos e metadados

O diretório do job contém:

- `model.glb`: geometria original, sempre preservada;
- `texture_work/white_mesh.obj`: entrada do Paint com materiais e UVs válidos;
- `texture_work/textured_mesh.obj` e arquivos MTL/texturas associados;
- `model_textured.glb`: resultado final com materiais;
- `paint_metadata.json`: metadados emitidos pelo wrapper oficial;
- `texture_metadata.json`: metadados públicos do pipeline Forge3D.

Os metadados públicos não contêm caminhos internos. Registram engine, versão,
resolução, qualidade, duração, tamanho e mapas PBR encontrados.

## Falhas

Uma falha é persistida sem invalidar o shape original:

```json
{
  "status": "error",
  "step": "paint",
  "message": "Falha na etapa paint"
}
```

Os passos possíveis são `glb_to_obj`, `paint` e `obj_to_glb`. Em produção, o
stderr dos subprocessos não é exposto pela API.

## Validação GPU

```bash
cd /workspace/forge3d-ai
export RUN_TEXTURE_GPU_TESTS=1
export FORGE3D_TEXTURE_TEST_JOB_ID=<job-shape-completed>
export FORGE3D_TEST_API_URL=http://127.0.0.1:8000
backend/scripts/test_texture_gpu.sh
```

Validação completa automática, usando `robot.png`:

```bash
python3 backend/scripts/test_texture_e2e.py \
  --image /workspace/forge3d-ai/examples/robot.png \
  --api-url http://127.0.0.1:8000
```

Para validar também parada e reinício da porta 8080:

```bash
python3 backend/scripts/test_full_hunyuan_pipeline.py \
  --image /workspace/forge3d-ai/examples/robot.png
```
