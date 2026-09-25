# Sign-in

A small session layer for local development and demos. No new dependencies.

## How it works

| Piece | Implementation |
|---|---|
| Accounts | `users` table: email (unique, case-insensitive), name, password hash, organisation |
| Passwords | PBKDF2-HMAC-SHA256, 240,000 iterations, random salt per user (Python standard library) |
| Sessions | `auth_sessions` table. A random 256-bit token is given to the browser once; only its SHA-256 is stored |
| Lifetime | `SESSION_TTL_HOURS`, default 336 (14 days). Expired sessions are refused and deleted |
| Sign-out | Deletes the session row, so the token stops working at once. Other browsers stay signed in |
| Organisation | Taken from the user's account on every request. The browser cannot choose it |

## Endpoints

| Method | Path | Notes |
|---|---|---|
| POST | `/api/auth/login` | `{email, password}` returns `{token, expiresAt, user}`. Wrong email and wrong password get the same 401 |
| GET | `/api/auth/me` | The signed-in user, or 401 |
| POST | `/api/auth/logout` | Ends the session. 204, also when already signed out |

Every other business route needs `Authorization: Bearer <token>`. Without it: 401 with
`WWW-Authenticate: Bearer`. The frontend treats any 401 as "session ended" and returns to sign-in.

## Accounts

- **Demo account**, created or updated on every start from `DEMO_USER_EMAIL`, `DEMO_USER_PASSWORD` and
  `DEMO_USER_NAME`, in the default organisation (`org_default`). Defaults:
  `demo@knowledgepulse.local` / `knowledgepulse`. An empty password creates no demo user. The API logs a
  warning while the default password is in use.
- **More accounts**: `python scripts/create_user.py --email asha@example.com --name Asha`
  (add `--organization-id org_acme` for another organisation; prompts for the password).

## Frontend

- `/login` is the only page reachable signed out; everything else redirects there and comes back after
  sign-in.
- The session is kept in `localStorage` (`kp.session`) until it expires or the user signs out, and is
  checked with `/api/auth/me` on each page load.
- The account menu shows the user, switches and creates workspaces, and signs out.
- The selected workspace is remembered per organisation (`kp.workspace.<org>`) and sent as
  `X-Workspace-Id`.

## Before this faces the internet

Deliberately left out, and needed for a public deployment: set a strong `DEMO_USER_PASSWORD` (or
empty it), rate limiting on sign-in, password reset, and an admin screen for accounts. Tokens in
`localStorage` are readable by any script running on the page, so keep third-party scripts off it.
