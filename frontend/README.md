# Investment X Buddy — Frontend

Next.js App Router frontend for a transparent AI investment-research workspace. The default is an explicit local Demo Mode; no DeepSeek or financial-data API is called.

## Run locally

```bash
npm install
npm run dev
```

Open `http://localhost:3000`. Production verification:

```bash
npm run typecheck
npm run lint
npm run build
npm start
```

## FastAPI mode

Copy `.env.example` to `.env.local` inside `frontend/` and set:

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

The adapter is centralized in `src/lib/research-gateway.ts`. It reserves these endpoints:

- `POST /api/v1/runs`
- `GET /api/v1/runs/{id}`
- `POST /api/v1/runs/{id}/approve`
- `POST /api/v1/runs/{id}/resume`
- `POST /api/v1/runs/{id}/cancel`
- `GET /api/v1/runs/{id}/events`
- `GET /api/v1/runs/{id}/evidence`
- `GET /api/v1/runs/{id}/report`
- `GET /api/v1/threads`
- `GET /api/v1/tools`

API responses are mapped in `src/lib/research-gateway.ts`. The UI polls active runs every 1.5 seconds, stops at terminal states, persists the active `run_id` in local storage, and reloads it after a page refresh. API errors remain visible and never silently become a successful Demo run; the user can explicitly switch to Demo Mode. Fixture evidence stays labeled `DEMO DATA`. Never put backend API keys in a `NEXT_PUBLIC_*` variable.

## Netlify

Connect the GitHub repository to Netlify. The committed root `netlify.toml` defines these build settings:

- Base directory: `frontend`
- Build command: `npm run build`
- Publish directory: `.next`
- Node.js: `24`

Netlify applies its current OpenNext adapter automatically; this project does not pin or install a Netlify Next.js plugin.

Leave `NEXT_PUBLIC_API_BASE_URL` unset while the Render backend is unavailable. The production build then stays in the existing Demo Mode. After Render is public, add this variable under **Project configuration → Environment variables** using the backend HTTPS origin without `/api/v1`, then redeploy:

```env
NEXT_PUBLIC_API_BASE_URL=https://your-render-service.onrender.com
```

The Render service must set `CORS_ORIGINS` to a JSON array containing the exact Netlify production origin. Do not put `DEEPSEEK_API_KEY`, financial API keys, or database credentials in Netlify or any `NEXT_PUBLIC_*` variable.
