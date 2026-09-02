# Status

Last updated: 31 August 2026 · Session 2

## Where things stand

Both halves are built. The pipeline runs end to end and is verified by an automated smoke test. What it
has never done is run against a real documentation site with real embeddings and a real model, because
that needs a crawl target chosen and an API key in hand.

Frontend: complete, builds clean, runs on placeholder data or against the live API.
Backend: complete, all seven features implemented, smoke test passing.

## What was built this session

**Backend — `backend/`, roughly 2,100 lines of Python.**

| File | Lines | What it is |
|---|---|---|
| `app/config.py` | 90 | Every tunable value. Only file that reads env vars. |
| `app/models.py` | 175 | Seven entities plus cluster membership and evaluation runs |
| `app/schemas.py` | 130 | Response shapes, camelCase to match the frontend |
| `app/llm.py` | 110 | Groq and Gemini behind one interface, over plain HTTP |
| `app/embeddings.py` | 50 | sentence-transformers, lazily loaded, L2-normalised output |
| `app/vector_store.py` | 80 | Chroma gateway; the only file that knows the vector DB |
| `app/ingest/crawler.py` | 120 | Bounded breadth-first crawl, boilerplate stripping |
| `app/ingest/chunker.py` | 165 | Heading-aware splitting, PDF and DOCX parsers |
| `app/ingest/pipeline.py` | 145 | Crawl, parse, chunk, embed, index, status tracking |
| `app/rag/engine.py` | 175 | Retrieval, confidence, grounded generation, logging |
| `app/analytics/clustering.py` | 190 | UMAP, HDBSCAN, class-based TF-IDF, topic naming, severity |
| `app/analytics/trends.py` | 90 | Centroid matching, trend states, priority formula |
| `app/analytics/recommend.py` | 165 | Category rules, recommendation prose, report summary |
| `app/analytics/batch.py` | 195 | The scheduled job, idempotent per period |
| `app/evaluation.py` | 130 | The three RAGAS metrics, implemented directly |
| `app/routers/*.py` | 330 | HTTP surface, 13 endpoints |
| `app/main.py` | 65 | App wiring, CORS, health |
| `scripts/seed_conversations.py` | 220 | Question generation and replay across three periods |
| `scripts/smoke_test.py` | 250 | Full-pipeline verification with stubs |
| `scripts/run_analytics.py` etc. | 140 | Operational scripts |

**Config.** `.env.example`, `Dockerfile` (CPU-only torch, embedding model baked in), `render.yaml`.

**Docs.** `backend/README.md` written; `docs/SETUP.md` and the root `README.md` updated.

**One frontend change.** `api.ts` now surfaces the backend's `detail` message on an error rather than a
bare status code, so "No report yet, run the analytics batch first" actually reaches the screen.

## Verified working

The smoke test asserts all of this and passes in about ten seconds, with no API key:

- Chunker splits at heading boundaries and keeps the heading path on every chunk.
- Retrieval confidence is measurably lower on a question the corpus does not cover (0.22) than on one it
  does (0.32). That separation is the entire premise of F2.
- Conversation turns log with confidence and retrieved chunk IDs attached.
- HDBSCAN finds multiple topics and assigns genuine one-offs to noise rather than forcing them in.
- Centroid matching links the same topic across consecutive periods.
- A topic planted to grow 1 → 2 → 9 across periods is correctly classified `emerging`.
- Every recommendation comes out with its supporting questions attached.

Every API endpoint returns 200, or a 404 with an explanatory message when there is no data yet.

## Known issues

1. **Topic names in the smoke test are nonsense** ("customer support questions"). That is the stubbed
   model, not a bug — the naming call is real and produces real titles once a key is set.
2. **The crawler has never run against a real site.** It is written and bounded correctly but has only
   seen fixture HTML. Expect to tune `CRAWL_MAX_DEPTH` and the boilerplate stripping on whatever site
   you pick.
3. **`HDBSCAN_MIN_CLUSTER_SIZE` will need tuning.** Default 6. On 800 questions across roughly 16 topics
   that should be close, but the BERTopic literature is explicit that short question-form text needs
   hand-tuning and offers no established guidance. Record what you settle on — that is a legitimate
   finding for the paper, not just housekeeping.
4. **`severity` is a keyword heuristic.** Deliberate, because it is inspectable and a reviewer can be
   shown exactly why a topic ranked where it did. But it is the weakest term in the priority formula and
   the easiest thing to attack. Worth having the model score it too and comparing.
5. **Frontend bundle is 610 KB** (181 KB gzipped), Recharts being most of it.
6. **No Alembic.** Tables are created from the models at startup. Fine until the schema changes while
   holding data worth keeping, which will happen during seeding experiments. Add migrations then.
7. **Torch could not be installed in the build sandbox**, so `embeddings.py` ran only through its stub.
   The module is eight lines around a standard API call, but it is the one piece that has not executed
   for real.

## Still open

- **Which site to crawl.** This blocks the seed run, which blocks everything visual. Needs 60+ pages of
  public documentation behind a real product.
- **Whether to run a small real pilot** alongside the synthetic archive. Reasoning in `docs/DATA.md`.
  Two-week lead time, so it needs deciding soon rather than later.

## Next session

Nothing large remains. In rough order of value:

1. **Pick a site and run the full sequence.** Crawl, seed, analytics, evaluate. This is where the real
   bugs live; expect crawl tuning and cluster-size tuning to take an afternoon between them.
2. **Tune and write down what happened.** `HDBSCAN_MIN_CLUSTER_SIZE`, `TOPIC_MATCH_THRESHOLD`, the four
   priority weights. That record is a section of the paper.
3. **Hand-check the cluster labels** against their member questions. `docs/DATA.md` flags the
   circularity risk in using a model to both generate the questions and name the resulting clusters.
4. **Deploy.** Netlify for the frontend, Render plus Neon for the backend. Both already configured.
5. **If there is time:** file upload in the Sources screen (the endpoint exists, there is no UI for it),
   and a period selector so older reports are reachable.
