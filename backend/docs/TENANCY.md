# Tenancy

Two levels, one inside the other.

| Level | Decided by | Required | What it isolates |
|---|---|---|---|
| Organisation | The signed-in user's account (see `docs/AUTH.md`) | Yes, on every business route | Everything. The tenant. |
| Workspace | `X-Workspace-Id` | No | A profile inside one organisation: its own sources, chat archive, topics, reports, evaluation runs and chunk settings |

Each user belongs to one organisation. Several users can share an organisation
(create them with `scripts/create_user.py --organization-id`).

## How the organisation is decided

`app/tenant.py:get_organization_id`, in this order:

1. `Authorization: Bearer <token>` from `/api/auth/login`: the session's user's organisation. If the
   request also sends `X-Organization-Id` and it is a different organisation: 403.
2. Otherwise `X-Organization-Id` is accepted only with a correct `X-Internal-Key` (`INTERNAL_API_KEY`).
   That is the server-to-server path. The header is then validated: 1-64 of `a-z A-Z 0-9 _ -`,
   400 if missing or malformed.
3. Otherwise 401 "Sign in to continue."

The browser never sends `X-Organization-Id`; it is an internal backend concern.
Public routes: `GET /api/health`, `GET /api/research/latest` (the project's own chunking experiment,
not tenant data), and sign-in itself.

There is no organisations table. An organisation exists as soon as a user belongs to it.

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

Two options, both supported:

- The Next.js frontend signs users in through `/api/auth/login` and sends the bearer token, exactly as
  the Vite frontend does.
- A Next.js server that authenticates users itself (for example against MongoDB) calls FastAPI
  server-to-server with `X-Internal-Key` and `X-Organization-Id`. Keep `INTERNAL_API_KEY` secret and
  out of the browser; anyone holding it can act for any organisation.

## Tests

```bash
python -m unittest tests/test_multitenancy.py   # header rules, isolation, cross-tenant 404s, migration
python scripts/smoke_test.py                     # full pipeline, plus the HTTP tenant boundary
```
