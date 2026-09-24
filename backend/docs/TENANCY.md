# Tenancy

Two levels, one inside the other.

| Level | Header | Required | What it isolates |
|---|---|---|---|
| Organisation | `X-Organization-Id` | Yes, on every business route | Everything. The tenant. |
| Workspace | `X-Workspace-Id` | No | A profile inside one organisation: its own sources, chat archive, topics, reports, evaluation runs and chunk settings |

One user is one organisation for now. Several users per organisation is a later milestone.

## The organisation header

- Format: 1 to 64 characters of `a-z A-Z 0-9 _ -`.
- Missing or blank: `400 "X-Organization-Id header is required."`
- Malformed: `400 "Invalid X-Organization-Id header format. ..."`
- HTTP requests never fall back to a default organisation.
- Public, no header: `GET /api/health`, `GET /api/research/latest` (the project's own chunking experiment, not tenant data).

There is no organisations table. An organisation exists as soon as a request names it.

## Workspaces inside an organisation

- Every organisation has a default workspace, created on its first request. Its id is derived from the
  organisation id, so there is exactly one, and it cannot be deleted.
- `org_default` is the organisation that owns everything created before tenancy. Its default workspace
  is the original `ws_default`, so existing data stays where it was.
- Without `X-Workspace-Id`, a request uses the organisation's default workspace.
- `X-Workspace-Id` naming another organisation's workspace is a 404, the same as a workspace that does
  not exist. So is PATCH or DELETE of another organisation's workspace.
- `GET /api/workspaces` lists only the caller's workspaces, default first, each with `isDefault`.

## Where it is enforced

The organisation is checked once, in `app/workspaces.py:current_workspace`, which every business route
depends on. It resolves the workspace and refuses one that belongs to anyone else. Every query below it is
scoped to that workspace.

On top of that:

- Every tenant-owned row carries `organization_id` (workspaces, sources, chunks, conversations, messages,
  topic clusters, cluster members, reports, recommendations, evaluation runs), stamped from the workspace
  when the row is written. Neither `organization_id` nor `workspace_id` has a default, so a row written
  without them fails instead of landing in someone else's data.
- Chroma metadata carries both ids, and every search filters on both inside Chroma.
- Source and insight lookups by id check both the workspace and the organisation.

## Database

Upgraded in place on every start by `app/migrate.py`, on SQLite and Postgres:

- `organization_id` is added where missing, with `org_default` for existing rows.
- `workspace_id` is added where missing, with `ws_default` for existing rows.
- A database from the organisation-only branch (organisation ids but no workspaces) has each non-default
  organisation's rows moved into that organisation's own default workspace.
- The single-column and composite indexes from `app/models.py` are created if missing.
- Existing Chroma chunks are tagged with both ids at start-up.

No separate migration script is needed.

## Scripts

All take `--organization-id` and `--workspace`:

- Only `--workspace`: that workspace, whatever organisation owns it.
- Only `--organization-id`: that organisation's default workspace.
- Both: the workspace, refused if it belongs to another organisation.
- Neither: `org_default`'s default workspace (`ws_default`).

## Next.js integration

The Next.js app derives `organization_id` from the signed-in user and sends `X-Organization-Id` on every
server-to-server call to FastAPI. Authentication stays in Next.js.

The header is only as trustworthy as whoever sets it. Until Next.js sits in front, the Vite frontend
sets it from `VITE_ORGANIZATION_ID` in the browser, which anyone can change: that gives separation of
data, not security. Once Next.js is in front, FastAPI should accept calls only from it (a private network,
or a shared secret header checked in `get_organization_id`).

## Tests

```bash
python -m unittest tests/test_multitenancy.py   # header rules, isolation, cross-tenant 404s, migration
python scripts/smoke_test.py                     # full pipeline, plus the HTTP tenant boundary
```
