from __future__ import annotations

import re
from typing import TYPE_CHECKING

from fastapi import Header, HTTPException
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from app.models import Source, TopicCluster

ORG_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def get_organization_id(
    x_organization_id: str | None = Header(
        None,
        alias="X-Organization-Id",
        description="Tenant identifier for organization-scoped data isolation.",
    ),
) -> str:
    """Validate and extract the organization tenant ID from the X-Organization-Id header.

    Rejects missing, blank, or malformed headers with HTTP 400.
    Never defaults to org_default for HTTP requests.
    """
    if not x_organization_id:
        raise HTTPException(status_code=400, detail="X-Organization-Id header is required.")

    org_id = x_organization_id.strip()
    if not org_id:
        raise HTTPException(status_code=400, detail="X-Organization-Id header is required.")

    if not ORG_ID_REGEX.match(org_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid X-Organization-Id header format. Must be 1-64 alphanumeric characters, underscores, or hyphens.",
        )

    return org_id


def get_source_for_organization(
    session: Session, source_id: str, organization_id: str
) -> Source | None:
    """Fetch a Source strictly scoped to the specified organization."""
    from app.models import Source

    return (
        session.query(Source)
        .filter(Source.id == source_id, Source.organization_id == organization_id)
        .one_or_none()
    )


def get_insight_for_organization(
    session: Session, insight_id: str, organization_id: str
) -> TopicCluster | None:
    """Fetch a TopicCluster insight strictly scoped to the specified organization."""
    from app.models import TopicCluster

    return (
        session.query(TopicCluster)
        .filter(TopicCluster.id == insight_id, TopicCluster.organization_id == organization_id)
        .one_or_none()
    )
