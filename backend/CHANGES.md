# Changes in this round: sign-in and persistent conversations

## New
- **Sign-in.** Accounts and sessions (`users`, `auth_sessions`), `/api/auth/login`,
  `/api/auth/me`, `/api/auth/logout`. Demo account in `org_default` created on
  start from `DEMO_USER_*` settings. `scripts/create_user.py` for more. No new
  dependencies. See `docs/AUTH.md`.
- **Conversation history.** `GET /api/chat/history?session_id=...` returns a
  conversation's turns. Answers now store their citations (`messages.citations`,
  added by the start-up migration), so they reload intact even after a reindex.
- **Frontend:** a sign-in page, protected routes, a session kept across reloads,
  and an account menu with the user, workspace switching and Sign out.
- **Ask page:** the conversation survives moving between pages and reloads, is
  kept per workspace, and has a New conversation button.
- **Tests:** `test_auth.py`, conversation-history tests, acceptance for AUTH1-4
  and CHAT1, and a browser test (`tests/e2e/run_e2e.py`, optional, Playwright).

## Changed
- The organisation now comes from the signed-in account. `X-Organization-Id` is
  internal: accepted only with `X-Internal-Key` (`INTERNAL_API_KEY`), for a
  trusted server. Without a session every business route answers 401.
- `VITE_ORGANIZATION_ID` and `VITE_ACCOUNT_NAME` are gone from the frontend.
- Chat timestamps are marked as UTC, so browsers no longer read them as local time.
- curl examples in the README and SETUP now sign in first.

## Fixed
- Questions vanished when leaving the Ask page, and a reload started a new
  conversation: the conversation lived in the page's own state and the session id
  was regenerated on every load.

---

# Changes in this round: multi-tenancy

Merges the organisation-level tenancy from the multitenancy branch into
workspaces. An organisation (`X-Organization-Id`) owns workspaces
(`X-Workspace-Id`). Full reference: `docs/TENANCY.md`.

## New
- `app/tenant.py`: validates `X-Organization-Id` (required on every business
  route, 400 if missing or malformed), and gives every organisation its own
  default workspace, created on first use.
- `organization_id` on every tenant-owned table, with the branch's composite
  indexes. Chroma chunks carry it too, and searches filter on it.
- `isDefault` on workspaces, so the frontend no longer hard-codes `ws_default`.
- Scripts take `--organization-id` alongside `--workspace`.
- `tests/test_multitenancy.py`: isolation tests for both levels, plus the migration.
- Smoke test step 6 checks the tenant boundary over HTTP.

## Changed
- Requests without `X-Workspace-Id` now use the caller's organisation's default
  workspace, not the global `ws_default`. Another organisation's workspace id is a 404.
- The start-up migration adds `organization_id` (existing rows go to
  `org_default`) and creates missing indexes. The branch's
  `scripts/migrate_multitenancy.py` is not needed.
- `workspace_id` no longer defaults to `ws_default` in the models: a row written
  without it fails rather than landing in the default workspace.
- Smoke test fixed: it had been failing at step 2 since workspaces were added,
  because the fixture chunks had no workspace id.

## Frontend
- Sends `X-Organization-Id` from `VITE_ORGANIZATION_ID` (default `org_default`).
- The saved workspace is remembered per organisation.

---

# Changes in the previous round

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
