# Architecture

## The one idea

Two paths through the system that never block each other.

The **read path** is the chatbot. A customer asks something, the retriever pulls the closest passages
from the index, the model writes an answer from them, and the whole turn — question, answer, which
chunks came back, how similar they were — gets appended to a log. This runs in a couple of seconds and
has to stay that fast.

The **analysis path** is a scheduled job. Once a month it reads everything in that log, clusters the
questions into topics, compares each topic against previous months, ranks them, and writes a report. It
takes minutes, nobody is waiting on it, and if it fails the chatbot carries on unaffected.

Keeping these apart is the reason the analytics can be as slow and expensive as it needs to be.

## Layers

```
  Chat widget          Admin console         Insights dashboard      ← what people see
  ─────────────────────────────────────────────────────────────
  Chat API             Ingestion API         Insights & report API   ← FastAPI
  ─────────────────────────────────────────────────────────────
  RAG engine           Ingestion pipeline    Batch analytics engine  ← the work
  ─────────────────────────────────────────────────────────────
  Vector store         Postgres              Uploaded files          ← storage
```

A scheduler triggers the analytics engine. An external LLM API is called by the RAG engine (for answers)
and by the analytics engine (for topic names and report prose). Nothing else talks to the outside world.

## Frontend

Plain Vite SPA. React Router for navigation, Recharts for the two charts, no state management library
and no data-fetching library, because the app reads six endpoints and writes one. A twenty-line
`useAsync` hook in `src/lib/format.ts` covers it. Adding TanStack Query here would be weight without
benefit.

```
src/
├── main.tsx              Routes
├── index.css             Design tokens applied to base elements
├── components/
│   ├── Shell.tsx         Left rail and page frame
│   └── ui.tsx            Page header, stats, tags, buttons, empty and error states
├── pages/                One file per route
├── lib/
│   ├── api.ts            Every network call. Mock/real switch lives here.
│   ├── types.ts          Mirrors the backend data model
│   └── format.ts         Number formatting, plain-English labels, useAsync
└── mock/data.ts          Placeholder dataset shaped like real API responses
```

### The mock switch

`api.ts` checks `VITE_API_BASE_URL`. Empty means every function returns data from `mock/data.ts` after a
short artificial delay, so loading states are real and not hypothetical. Set it, and the same functions
hit HTTP. No component knows the difference — this is why the frontend could be finished first.

### Design system

Colour, type and spacing tokens live in `tailwind.config.js` and nowhere else. Six named colours,
three typefaces with one job each, a type scale in `theme.fontSize`.

The interface is built as a ledger rather than a card grid, which is a deliberate fit to the subject:
the product's whole premise is reading an archive of records, so records separated by hairline rules read
more honestly than the same content chopped into rounded boxes. The one flourish is the priority bar — a
faint oxblood wash bleeding behind each insight row, width proportional to its priority score, so
ranking is visible before you read a word. Everything else stays quiet.

Fraunces carries display type, Inter carries reading text, JetBrains Mono is reserved strictly for
numbers, IDs and anything the user might compare column-wise. Mono never appears as a decorative label.

## Backend, planned

Modules follow Section 7.2.5 of the report:

| Module | Job |
|---|---|
| `source_manager` | Registers sources, computes content hashes, decides when to re-index |
| `crawler` | Follows internal links from an entry point within a depth and domain boundary |
| `ingest_pipeline` | Parses, cleans, chunks at heading boundaries, embeds |
| `vector_gateway` | Thin wrapper over the vector store: upsert, delete, top-k search |
| `rag_engine` | Embeds the question, retrieves, scores confidence, builds the prompt, returns citations |
| `conversation_store` | Persists turns with confidence and retrieved chunk IDs |
| `analytics_batch` | Selects the window, embeds, reduces, clusters, labels |
| `trend_tracker` | Matches topics across periods, classifies recurring / emerging / stable |
| `insight_prioritiser` | Scores and ranks, links each insight to its member questions |
| `recommendation_engine` | Assigns insights to one of four action categories |
| `report_builder` | Assembles the periodic client report with evidence |
| `evaluation_harness` | Runs the held-out set, records faithfulness and relevance |

### Decisions already made

**HDBSCAN from scikit-learn, not the standalone package.** Same algorithm. The standalone `hdbscan`
package needs a compiler and breaks regularly on Windows; scikit-learn has shipped it natively since
1.3 and installs from a wheel every time.

**ChromaDB for the vector store**, file-backed, matching the report. If the deployment image gets awkward
we move to pgvector inside the same Postgres and change one file, `vector_gateway`.

**Confidence from retrieval, not from the model.** The score is derived from the similarity distribution
of the top-k chunks and computed *before* the generator runs. This is the point of F2: a model will
happily write a confident paragraph with nothing behind it, so asking it how sure it feels tells you
nothing about whether the corpus contained the answer. Similarity does.

**Two LLM providers, one interface.** Groq during development because it is free and fast enough to
iterate against; Gemini for the demo. A single `llm` module with two adapters and a config switch, so
neither choice leaks into the rest of the code.
