"""Which organisation a request belongs to.

Two levels of isolation:

    organisation  - the tenant. Taken from the signed-in user's session. Never
                    chosen by the browser and never defaulted for HTTP.
    workspace     - a profile inside one organisation (X-Workspace-Id, optional).

How a request's organisation is decided (get_organization_id):

    1. "Authorization: Bearer <token>": the session's user's organisation. If the
       request also names an organisation in X-Organization-Id and it is not that
       one, 403. This is how the browser app works.
    2. Otherwise, X-Organization-Id is accepted only together with a correct
       X-Internal-Key (settings.internal_api_key). This is the server-to-server path,
       for a trusted backend such as a Next.js server or a test harness.
    3. Otherwise, 401.

The organisation is checked once, where the workspace is resolved
(app.workspaces.current_workspace). Every query below that is scoped to a
workspace that is already known to belong to the caller's organisation, so the
two cannot disagree.

Every organisation has a default workspace, created on first use. Its id is
derived from the organisation id, so there is exactly one per organisation and
no extra column is needed to find it. The default organisation keeps the
original "ws_default", which is where all pre-tenancy data lives.
"""

from __future__ import annotations

import hashlib
import hmac
import re

from fastapi import Depends, Header, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import bearer_token, require_session
from app.config import settings
from app.db import get_db
from app.models import DEFAULT_WORKSPACE_ID, Workspace

ORG_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def _validated(org_id: str | None) -> str:
    org_id = (org_id or "").strip()
    if not org_id:
        raise HTTPException(status_code=400, detail="X-Organization-Id header is required.")
    if not ORG_ID_REGEX.match(org_id):
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid X-Organization-Id header format. Must be 1-64 alphanumeric "
                "characters, underscores, or hyphens."
            ),
        )
    return org_id


def get_organization_id(
    token: str | None = Depends(bearer_token),
    x_organization_id: str | None = Header(
        None,
        alias="X-Organization-Id",
        description="Server-to-server only, with X-Internal-Key. Browsers sign in instead.",
    ),
    x_internal_key: str | None = Header(None, alias="X-Internal-Key"),
    db: Session = Depends(get_db),
) -> str:
    """The organisation this request acts for. See the module docstring for the rules."""
    if token:
        org_id = require_session(db, token).user.organization_id
        requested = (x_organization_id or "").strip()
        if requested and requested != org_id:
            raise HTTPException(403, "This account does not belong to that organisation.")
        return org_id

    key = settings.internal_api_key
    if key and x_internal_key and hmac.compare_digest(x_internal_key, key):
        return _validated(x_organization_id)

    raise HTTPException(401, "Sign in to continue.", headers={"WWW-Authenticate": "Bearer"})


def default_workspace_id(organization_id: str) -> str:
    """The id of an organisation's default workspace. Stable and unique per org."""
    if organization_id == settings.default_organization_id:
        return DEFAULT_WORKSPACE_ID
    return f"ws_d_{hashlib.sha1(organization_id.encode()).hexdigest()[:16]}"


def ensure_default_workspace(db: Session, organization_id: str) -> Workspace:
    """Return the organisation's default workspace, creating it on first use."""
    workspace_id = default_workspace_id(organization_id)
    workspace = db.get(Workspace, workspace_id)
    if workspace is not None:
        return workspace
    workspace = Workspace(
        id=workspace_id,
        organization_id=organization_id,
        name="Default workspace",
        description="",
    )
    db.add(workspace)
    try:
        db.commit()
    except IntegrityError:
        # Two first requests raced; the other one created it.
        db.rollback()
        workspace = db.get(Workspace, workspace_id)
    return workspace


def organization_of(db: Session, workspace_id: str) -> str:
    """The organisation a workspace belongs to. Used to stamp new rows."""
    workspace = db.get(Workspace, workspace_id)
    if workspace is None:
        raise LookupError(f"No workspace {workspace_id}")
    return workspace.organization_id


def resolve_workspace(
    db: Session, workspace_id: str | None = None, organization_id: str | None = None
) -> Workspace:
    """For scripts: pick a workspace from --workspace and/or --organization-id.

    Only a workspace: that workspace. Only an organisation: its default
    workspace. Both: the workspace, checked against the organisation. Neither:
    the default organisation's default workspace.
    """
    if workspace_id:
        workspace = db.get(Workspace, workspace_id)
        if workspace is None:
            raise SystemExit(f"No workspace {workspace_id}.")
        if organization_id and workspace.organization_id != organization_id:
            raise SystemExit(f"Workspace {workspace_id} does not belong to {organization_id}.")
        return workspace
    return ensure_default_workspace(db, organization_id or settings.default_organization_id)
