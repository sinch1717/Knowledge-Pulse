"""Which workspace a request belongs to.

The frontend sends `X-Workspace-Id` on every call. Requests without it (curl,
the old frontend, scripts) fall into the default workspace, so nothing that
worked before breaks.
"""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import DEFAULT_WORKSPACE_ID, Workspace


def current_workspace(
    x_workspace_id: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Workspace:
    workspace_id = x_workspace_id or DEFAULT_WORKSPACE_ID
    workspace = db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(404, f"No workspace {workspace_id}. It may have been deleted; pick another.")
    return workspace
