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

A aplicação fica em `http://localhost:3000`. Configure o backend em:

```text
NEXT_PUBLIC_FORGE3D_API_URL=http://127.0.0.1:8000
```

O frontend usa exclusivamente `POST /jobs/generate`, acompanha o job em
`GET /jobs/{job_id}` e abre o artefato por `GET /download/{job_id}`.

## Qualidade

```bash
npm run typecheck
npm run lint
npm test
npm run build
```

O diretório `frontend/` na raiz é legado e não faz parte da aplicação ativa.
