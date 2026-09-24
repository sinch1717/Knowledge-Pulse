from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import vector_store
from app.config import settings
from app.db import get_db
from app.ingest import cancel
from app.models import (
    Conversation,
    EvaluationRun,
    Message,
    Report,
    Source,
    TopicCluster,
    Workspace,
)
from app.schemas import WorkspaceCreate, WorkspaceOut, WorkspaceUpdate
from app.tenant import default_workspace_id, ensure_default_workspace, get_organization_id

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])

# Sensible bounds, so a typo cannot produce one-word or book-length chunks.
MIN_TARGET, MAX_TARGET = 40, 2000
MAX_PAGES = 2000


def _validate(target: int | None, overlap: int | None, pages: int | None, current: Workspace | None = None) -> None:
    if target is not None and not MIN_TARGET <= target <= MAX_TARGET:
        raise HTTPException(400, f"Chunk size must be between {MIN_TARGET} and {MAX_TARGET} words.")
    effective_target = target or (current.chunk_target_words if current else None) or settings.chunk_target_words
    if overlap is not None and not 0 <= overlap < effective_target:
        raise HTTPException(400, "Overlap must be zero or more, and smaller than the chunk size.")
    if pages is not None and not 1 <= pages <= MAX_PAGES:
        raise HTTPException(400, f"Page limit must be between 1 and {MAX_PAGES}.")


def _owned(db: Session, workspace_id: str, organization_id: str) -> Workspace:
    """A workspace of the caller's organisation. Another organisation's is a plain 404."""
    ws = db.get(Workspace, workspace_id)
    if ws is None or ws.organization_id != organization_id:
        raise HTTPException(404, "No workspace with that id")
    return ws


def _out(db: Session, ws: Workspace) -> WorkspaceOut:
    sources = db.query(func.count(Source.id), func.coalesce(func.sum(Source.chunk_count), 0)).filter(
        Source.workspace_id == ws.id
    ).one()
    questions = (
        db.query(func.count(Message.id))
        .filter(Message.workspace_id == ws.id, Message.role == "customer")
        .scalar()
    )
    return WorkspaceOut(
        id=ws.id,
        name=ws.name,
        description=ws.description or "",
        chunkTargetWords=ws.chunk_target_words or settings.chunk_target_words,
        chunkOverlapWords=ws.chunk_overlap_words
        if ws.chunk_overlap_words is not None
        else settings.chunk_overlap_words,
        crawlMaxPages=ws.crawl_max_pages or settings.crawl_max_pages,
        usesDefaults=ws.chunk_target_words is None and ws.chunk_overlap_words is None,
        isDefault=ws.id == default_workspace_id(ws.organization_id),
        sourceCount=sources[0] or 0,
        chunkCount=int(sources[1] or 0),
        questionCount=questions or 0,
        createdAt=ws.created_at,
    )


@router.get("", response_model=list[WorkspaceOut])
def list_workspaces(db: Session = Depends(get_db), org: str = Depends(get_organization_id)):
    # A new organisation sees its default workspace on its very first visit.
    default = ensure_default_workspace(db, org)
    rows = (
        db.query(Workspace)
        .filter(Workspace.organization_id == org)
        .order_by(Workspace.created_at)
        .all()
    )
    rows.sort(key=lambda w: w.id != default.id)  # default first, then oldest first
    return [_out(db, w) for w in rows]


@router.post("", response_model=WorkspaceOut, status_code=201)
def create_workspace(
    payload: WorkspaceCreate, db: Session = Depends(get_db), org: str = Depends(get_organization_id)
):
    name = payload.name.strip()
    if not name:
        raise HTTPException(400, "Give the workspace a name.")
    _validate(payload.chunkTargetWords, payload.chunkOverlapWords, payload.crawlMaxPages)
    ensure_default_workspace(db, org)
    ws = Workspace(
        id=f"ws_{uuid.uuid4().hex[:10]}",
        organization_id=org,
        name=name[:120],
        description=payload.description.strip(),
        chunk_target_words=payload.chunkTargetWords,
        chunk_overlap_words=payload.chunkOverlapWords,
        crawl_max_pages=payload.crawlMaxPages,
    )
    db.add(ws)
    db.commit()
    return _out(db, ws)


@router.patch("/{workspace_id}", response_model=WorkspaceOut)
def update_workspace(
    workspace_id: str,
    payload: WorkspaceUpdate,
    db: Session = Depends(get_db),
    org: str = Depends(get_organization_id),
):
    ws = _owned(db, workspace_id, org)
    _validate(payload.chunkTargetWords, payload.chunkOverlapWords, payload.crawlMaxPages, ws)
    if payload.name is not None:
        if not payload.name.strip():
            raise HTTPException(400, "Give the workspace a name.")
        ws.name = payload.name.strip()[:120]
    if payload.description is not None:
        ws.description = payload.description.strip()
    # Chunk settings apply to the next index or reindex, not retroactively.
    fields = payload.model_fields_set
    if "chunkTargetWords" in fields:
        ws.chunk_target_words = payload.chunkTargetWords
    if "chunkOverlapWords" in fields:
        ws.chunk_overlap_words = payload.chunkOverlapWords
    if "crawlMaxPages" in fields:
        ws.crawl_max_pages = payload.crawlMaxPages
    db.commit()
    return _out(db, ws)


@router.delete("/{workspace_id}", status_code=204)
def delete_workspace(
    workspace_id: str, db: Session = Depends(get_db), org: str = Depends(get_organization_id)
):
    ws = _owned(db, workspace_id, org)
    if ws.id == default_workspace_id(org):
        raise HTTPException(400, "The default workspace cannot be deleted.")

    # Everything the workspace owns goes with it: vectors, chunks, the chat
    # archive, topics, reports and evaluation runs.
    for source in db.query(Source).filter(Source.workspace_id == ws.id).all():
        cancel.request_stop(source.id)
        vector_store.delete_source(source.id)
        db.delete(source)
    for model in (TopicCluster, Report, EvaluationRun):
        for row in db.query(model).filter(model.workspace_id == ws.id).all():
            db.delete(row)
    for conversation in db.query(Conversation).filter(Conversation.workspace_id == ws.id).all():
        db.delete(conversation)
    db.delete(ws)
    db.commit()
