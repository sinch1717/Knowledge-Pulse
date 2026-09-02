# Backend

FastAPI service. Two paths through it: a chat endpoint that answers from indexed
documents, and a batch job that reads the resulting conversations and works out what
customers are stuck on.

## Install

Python 3.11.

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

The first install is slow — sentence-transformers pulls PyTorch, which is around a
gigabyte. On Windows or Linux without a GPU you can halve that:

```bash
pip install torch==2.4.1 --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

## Check the wiring before spending API credit

```bash
python scripts/smoke_test.py
```

Runs the entire pipeline — ingest, retrieve, score confidence, log conversations,
cluster, compare periods, rank, write a report — against a fixture corpus, using a
stubbed embedder and a stubbed model. No API key, no model download, about ten
seconds. It asserts, among other things, that retrieval confidence is lower on a
question the corpus does not cover than on one it does, and that a topic planted to
grow across periods is correctly flagged as emerging.

If this passes, the plumbing is sound and anything that goes wrong afterwards is a
data or model problem rather than a code one.

## Run it for real

```bash
uvicorn app.main:app --reload
```

http://localhost:8000/api/health should report `"status": "ok"`. Interactive API
docs are at http://localhost:8000/docs.

Then, in order:

**1. Index a source.** Either through the frontend's Sources screen, or:

```bash
curl -X POST localhost:8000/api/sources \
  -H 'Content-Type: application/json' \
  -d '{"kind":"website","location":"https://docs.example.com"}'
```

Crawling runs in the background. Watch `GET /api/sources` until status reads
`ready`. A hundred pages takes two or three minutes, most of it the polite delay
between requests.

**2. Generate the conversation archive.**

```bash
python scripts/seed_conversations.py --questions 800
```

This reads the headings of what you just indexed, asks the model what customers
would realistically contact support about, generates questions in three planted
shapes — gaps the corpus does not cover, well-covered high-volume topics, and one
topic that spikes in the final period — then replays every question through the
live chat endpoint. Reasoning and limitations in [`../docs/DATA.md`](../docs/DATA.md).

Roughly 60 generation calls plus 800 answer calls. On Groq's free tier this takes
about twenty minutes and costs nothing. Use `--dry-run` to write the question set
without replaying it.

**3. Run the analytics.**

```bash
python scripts/run_analytics.py
```

Every period, oldest first, because each one needs the previous already clustered to
measure growth against. Two or three minutes for 800 questions.

**4. Evaluate.**

```bash
python scripts/build_eval_set.py --count 50
python scripts/run_evaluation.py
```

**5. Point the frontend at it.** In `frontend/.env`:

```
VITE_API_BASE_URL=http://localhost:8000
```

## Endpoints

| Method | Path | |
|---|---|---|
| GET | `/api/health` | Status and indexed chunk count |
| GET | `/api/overview` | Current period summary |
| GET | `/api/sources` | Registered sources |
| POST | `/api/sources` | Register a website, starts crawling |
| POST | `/api/sources/upload` | Upload a PDF, DOCX, TXT or MD |
| POST | `/api/sources/{id}/reindex` | Re-crawl and re-embed |
| DELETE | `/api/sources/{id}` | Remove a source and its vectors |
| POST | `/api/chat` | Ask a question. Logs the turn. |
| GET | `/api/insights` | Ranked topics for the current period |
| GET | `/api/insights/{id}` | One topic with its evidence |
| GET | `/api/reports/latest` | Most recent client report |
| POST | `/api/analytics/run` | Trigger the batch |
| GET | `/api/evaluation/latest` | Most recent evaluation run |

## Layout

```
app/
├── config.py            Every tunable value. The only file that reads env vars.
├── db.py                Engine and session
├── models.py            Seven entities from the report's data model
├── schemas.py           Response shapes; the contract with the frontend
├── llm.py               Groq and Gemini behind one interface
├── embeddings.py        Local sentence-transformers, lazily loaded
├── vector_store.py      Chroma gateway. Swap here to move to pgvector.
├── evaluation.py        The three RAGAS metrics, implemented directly
├── ingest/
│   ├── crawler.py       Bounded breadth-first crawl
│   ├── chunker.py       Heading-aware splitting, PDF and DOCX parsers
│   └── pipeline.py      Crawl, parse, chunk, embed, index
├── rag/engine.py        Retrieve, score confidence, generate, log
├── analytics/
│   ├── clustering.py    UMAP, HDBSCAN, class-based TF-IDF, topic naming
│   ├── trends.py        Cross-period matching, trend states, priority formula
│   ├── recommend.py     Category rules and recommendation prose
│   └── batch.py         The scheduled job
└── routers/             HTTP surface
```

## Two decisions worth knowing about

**Confidence is computed before generation, from retrieval similarity alone.** A
model will write a confident paragraph whether or not it had anything to work from,
so asking it how sure it is tells you nothing about whether your corpus held the
answer. Similarity does, and it stays meaningful months later when the generated
text is long gone. `rag/engine.py:compute_confidence`.

**The three evaluation metrics are implemented directly rather than by importing
`ragas`.** The package brings a large LangChain dependency tree that churns between
releases, and this project needs three metric definitions, not a framework. The
definitions follow the paper; see `evaluation.py`.

## Not on Vercel

Serverless functions cap the bundle at roughly 250 MB and time out after a minute.
sentence-transformers alone is larger than that, and the analytics batch runs for
minutes. Use Render (`render.yaml` is in this directory), Railway or Fly.io. The
Chroma index is file-backed, so whatever you use needs a persistent disk mount.
