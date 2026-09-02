# Setup

## What you need

- **Node.js 20 or 22.** Node 18 will work but 20 is what Netlify builds with, so match it locally.
- **Python 3.11**, once the backend exists. Not 3.12 or 3.13 — some of the clustering libraries lag a
  release or two behind and 3.11 is the version everything supports without argument.
- A **Groq** API key for development and a **Google Gemini** key for the demo. Neither is needed yet.

## Frontend

```bash
cd frontend
npm install
npm run dev
```

That is the whole thing. The app comes up at http://localhost:5173 on placeholder data, so you can look
at every screen before a single line of backend exists. A small amber note in the sidebar tells you when
you are on placeholder data, so there is no chance of demoing fake numbers by accident.

Other commands:

| Command | What it does |
|---|---|
| `npm run dev` | Development server with hot reload |
| `npm run build` | Type-check, then produce a production build in `dist/` |
| `npm run preview` | Serve the production build locally |
| `npm run lint` | Type-check only, no build |

### Connecting the backend later

Copy `frontend/.env.example` to `frontend/.env` and fill in one line:

```
VITE_API_BASE_URL=http://localhost:8000
```

Restart the dev server. Every screen switches from placeholder data to the real API. Nothing else
changes — all the network calls live in `frontend/src/lib/api.ts` and that file is the only place that
knows whether a backend exists.

If you leave `VITE_API_BASE_URL` empty, Vite's dev server also proxies `/api` to `localhost:8000`, so
either approach works locally.

## Backend

```bash
cd backend
# python3.11 -m venv .venv
py -3.11 -m venv venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # add your Groq key
python scripts/smoke_test.py       # ten seconds, no API key needed
uvicorn app.main:app --reload
```

The smoke test is worth running first. It exercises the whole pipeline against a fixture corpus with a
stubbed embedder and stubbed model, so if something is wired wrong you find out in ten seconds instead
of after a twenty-minute seeding run.

Getting from an empty database to a populated dashboard is four commands, in this order:

```bash
# 1. index a documentation site (or use the frontend's Sources screen)
curl -X POST localhost:8000/api/sources -H 'Content-Type: application/json' \
  -d '{"kind":"website","location":"https://docs.example.com"}'

# 2. generate and replay a conversation archive across three periods
python scripts/seed_conversations.py --questions 800

# 3. cluster, rank and write the report
python scripts/run_analytics.py

# 4. score the assistant
python scripts/build_eval_set.py --count 50
python scripts/run_evaluation.py
```

Step 2 is the long one — about twenty minutes on Groq's free tier. Full detail in
[`backend/README.md`](../backend/README.md), and the reasoning behind generating the archive at all is
in [`DATA.md`](./DATA.md).

## Deployment

**Frontend on Netlify.** Point Netlify at the repository. `frontend/netlify.toml` already sets the base
directory, the build command and the SPA redirect rule, so there is nothing to configure in the
dashboard except the `VITE_API_BASE_URL` environment variable.

**Backend, not on Vercel.** Vercel's serverless functions cap the deployment bundle at roughly 250 MB
and time out after a minute. The backend needs sentence-transformers, UMAP and HDBSCAN, and its
analytics batch runs for several minutes. It does not fit and it would not finish. Use Render's free web
service tier with a Neon Postgres instance, or Railway, or Fly.io. All three run a normal long-lived
process and all three have a free tier adequate for a demo.

## A note on dependency versions

Everything is pinned to an exact version, and none of them are the newest release. The React 18 /
Vite 5 / Tailwind 3 combination is what most production frontends were running through 2025 and into
2026: heavily documented, every edge case already answered on Stack Overflow, no migration surprises.
React 19 and Tailwind 4 are both fine, but for a project that has to be reproducible by someone reading
a paper in two years, boring is the right call.
