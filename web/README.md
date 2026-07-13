# Forge3D AI web

Frontend oficial do Forge3D AI, construído com Next.js, React, TypeScript,
Tailwind CSS e React Three Fiber.

## Desenvolvimento

```bash
cd web
cp .env.example .env.local
npm install
npm run dev
```

A aplicação fica em `http://localhost:3000`. Por padrão, o navegador usa
`/forge3d-api`, e o servidor Next encaminha as chamadas internamente ao FastAPI:

```text
FORGE3D_INTERNAL_API_URL=http://127.0.0.1:8000
```

Isso evita CORS e nunca envia o navegador do usuário para `127.0.0.1`. O
frontend usa `POST /api/v1/generate`, acompanha o job em
`GET /jobs/{job_id}` e abre o artefato por `GET /download/{job_id}`.

## Qualidade

```bash
npm run typecheck
npm run lint
npm test
npm run build
```

O diretório `frontend/` na raiz é legado e não faz parte da aplicação ativa.
Os componentes Next substituídos nesta sprint estão preservados em
`web/legacy/components/` e também não são importados pela aplicação.
