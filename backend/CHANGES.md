# Changes in this round

## New
- **Workspaces.** Fully separate profiles, each with its own sources, chat
  archive, topics, reports and evaluation runs. The frontend sends
  `X-Workspace-Id`; requests without it use the default workspace.
  Endpoints: `GET/POST /api/workspaces`, `PATCH/DELETE /api/workspaces/{id}`.
- **Per-workspace chunk settings.** Chunk size, overlap and page limit, set from
  the workspace settings dialog. They apply on the next index or reindex.
- **Stop.** `POST /api/sources/{id}/stop` stops a crawl or index within one page
  or one embedding batch. A partial crawl is never written to the index, and a
  source that was indexed before keeps its old chunks.
- **`GET /api/periods`** for the Insights period selector.
- **Research pipeline** in `research/`, with the runbook in `docs/RESEARCH.md`,
  and `GET /api/research/latest` for the website's Research page.

## Changed
- On start, the schema is upgraded in place: `workspace_id` is added to existing
  tables, all existing data lands in "Default workspace", and existing Chroma
  chunks are tagged. Sources left mid-crawl by a restart are reset instead of
  showing "indexing" forever.
- Adding a website that is already a source in the same workspace now returns
  409. Your current database has **two copies of plausible.io**, which puts every
  passage into retrieval twice; delete one from the Sources page.
- Chunker: an element nested in another block (a `<p>` inside an `<li>`) was
  indexed twice. Fixed. Reindex a source to pick this up.
- Scripts take `--workspace` (default `ws_default`).
