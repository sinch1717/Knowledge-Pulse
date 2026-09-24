"""Which workspace a request belongs to.

The organisation comes first: X-Organization-Id is required and validated by
app.tenant.get_organization_id. Within it, the frontend sends X-Workspace-Id.
Without that header the request uses the organisation's default workspace, so
curl and older clients keep working inside their own organisation.

A workspace id that belongs to a different organisation gets the same 404 as
one that does not exist, so ids cannot be probed across tenants.
"""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Workspace
from app.tenant import ensure_default_workspace, get_organization_id


def current_workspace(
    organization_id: str = Depends(get_organization_id),
    x_workspace_id: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Workspace:
    if not x_workspace_id:
        return ensure_default_workspace(db, organization_id)
    workspace = db.get(Workspace, x_workspace_id)
    if workspace is None or workspace.organization_id != organization_id:
        raise HTTPException(404, f"No workspace {x_workspace_id}. It may have been deleted; pick another.")
    return workspace
