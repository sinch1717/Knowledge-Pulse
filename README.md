# KnowledgePulse

A support chatbot that reads an organisation's own documentation, and — more to the point — an analytics
layer that reads the resulting conversation archive and tells the organisation what its customers are
stuck on.

Most chatbot products stop at deployment. The conversations pile up, nobody reads them, and a question
the bot cannot answer today it will fail to answer again tomorrow. KnowledgePulse treats that archive as
the asset: it clusters accumulated questions into topics, tracks which ones are growing, works out which
matter most, and turns the top of that list into specific instructions — change this in the product, fix
this page of the docs, add this FAQ entry, reply to these four people.

## Where the project stands

Both halves are built and the pipeline runs end to end. What remains is choosing a real documentation
site to crawl and running the seed. See [`status.md`](./status.md) for exactly what exists and what is
still open.

## Repository layout

```
knowledgepulse/
├── frontend/          Vite + React + TypeScript dashboard and chat interface
├── backend/           FastAPI service: ingestion, RAG, analytics batch
├── docs/
│   ├── SETUP.md       How to install and run
│   ├── ARCHITECTURE.md How the pieces fit together and why
│   └── DATA.md        Where the conversation data comes from
├── status.md          Current build status, known issues, next scope
└── README.md
```

## Quick start

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. No backend or API key needed — the interface serves placeholder data until
you set `VITE_API_BASE_URL`.

Full instructions in [`docs/SETUP.md`](./docs/SETUP.md).

## The seven features

| | Feature | Status |
|---|---|---|
| F1 | Grounded answers with visible citations | Done |
| F2 | Confidence taken from retrieval similarity, not the model's own claim | Done |
| F3 | Website crawling with structure-aware chunking | Done |
| F4 | Topic clustering with trend, recurrence and emergence | Done |
| F5 | Insight prioritisation | Done |
| F6 | Reference-free evaluation | Done |
| F7 | Recommendations across four action categories | Done |

Verify the lot in ten seconds with `cd backend && python scripts/smoke_test.py`.