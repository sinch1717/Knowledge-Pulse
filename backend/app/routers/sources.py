from __future__ import annotations

import os
import shutil
import uuid
from urllib.parse import urlparse

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.ingest import cancel
from app.ingest.pipeline import ingest_source
from app.models import Source, Workspace
from app.schemas import SourceCreate, SourceOut
from app.workspaces import current_workspace

router = APIRouter(prefix="/api/sources", tags=["sources"])

EXTENSION_KIND = {".pdf": "pdf", ".docx": "docx", ".txt": "text", ".md": "text"}
IN_FLIGHT = ("queued", "crawling", "indexing")


def _out(s: Source) -> SourceOut:
    return SourceOut(
        id=s.id,
        kind=s.kind,
        label=s.label,
        location=s.location,
        status=s.status,
        pageCount=s.page_count,
        chunkCount=s.chunk_count,
        lastIndexedAt=s.last_indexed_at,
        contentHash=s.content_hash,
        error=s.error,
    )


def _owned(db: Session, source_id: str, ws: Workspace) -> Source:
    source = db.get(Source, source_id)
    if source is None or source.workspace_id != ws.id or source.organization_id != ws.organization_id:
        raise HTTPException(404, "No source with that id in this workspace")
    return source


@router.get("", response_model=list[SourceOut])
def list_sources(db: Session = Depends(get_db), ws: Workspace = Depends(current_workspace)):
    rows = (
        db.query(Source)
        .filter(Source.workspace_id == ws.id)
        .order_by(Source.created_at.desc())
        .all()
    )
    return [_out(s) for s in rows]


@router.post("", response_model=SourceOut, status_code=201)
def create_source(
    payload: SourceCreate,
    tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    ws: Workspace = Depends(current_workspace),
):
    if payload.kind == "website" and not payload.location.startswith(("http://", "https://")):
        raise HTTPException(400, "A website source needs a full URL starting with http:// or https://")

    # Indexing the same site twice in one workspace doubles every retrieval hit.
    duplicate = (
        db.query(Source)
        .filter(Source.workspace_id == ws.id, Source.location == payload.location)
        .first()
    )
    if duplicate is not None:
        raise HTTPException(409, f"{payload.location} is already a source here. Reindex it instead.")

    label = payload.label or (
        urlparse(payload.location).netloc or os.path.basename(payload.location) or payload.location
    )
    source = Source(
        id=f"src_{uuid.uuid4().hex[:10]}",
        organization_id=ws.organization_id,
        workspace_id=ws.id,
        kind=payload.kind,
        label=label,
        location=payload.location,
        status="queued",
    )
    db.add(source)
    db.commit()

    tasks.add_task(ingest_source, source.id)
    return _out(source)


@router.post("/upload", response_model=SourceOut, status_code=201)
async def upload_source(
    tasks: BackgroundTasks,
    file: UploadFile = File(...),
    label: str | None = Form(default=None),
    db: Session = Depends(get_db),
    ws: Workspace = Depends(current_workspace),
):
    extension = os.path.splitext(file.filename or "")[1].lower()
    if extension not in EXTENSION_KIND:
        raise HTTPException(400, f"Cannot read {extension or 'that file type'}. Use PDF, DOCX, TXT or MD.")

    os.makedirs(settings.upload_path, exist_ok=True)
    source_id = f"src_{uuid.uuid4().hex[:10]}"
    destination = os.path.join(settings.upload_path, f"{source_id}{extension}")
    with open(destination, "wb") as out:
        shutil.copyfileobj(file.file, out)

    source = Source(
        id=source_id,
        organization_id=ws.organization_id,
        workspace_id=ws.id,
        kind=EXTENSION_KIND[extension],
        label=(label or "").strip() or file.filename or destination,
        location=destination,
        status="queued",
    )
    db.add(source)
    db.commit()

    tasks.add_task(ingest_source, source.id)
    return _out(source)


@router.post("/{source_id}/reindex", response_model=SourceOut)
def reindex(
    source_id: str,
    tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    ws: Workspace = Depends(current_workspace),
):
    source = _owned(db, source_id, ws)
    if source.status in IN_FLIGHT or source.status == "stopping":
        raise HTTPException(409, "This source is already being indexed. Stop it first.")
    cancel.clear(source.id)
    source.status = "queued"
    source.error = None
    db.commit()
    tasks.add_task(ingest_source, source.id)
    return _out(source)


@router.post("/{source_id}/stop", response_model=SourceOut)
def stop(source_id: str, db: Session = Depends(get_db), ws: Workspace = Depends(current_workspace)):
    """Ask a running crawl or index to stop. It finishes the page or batch it is on.

    The source keeps its previous chunks if it had any; a partial crawl is never
    written to the index.
    """
    source = _owned(db, source_id, ws)
    if source.status not in IN_FLIGHT:
        raise HTTPException(409, f"Nothing to stop: the source is {source.status}.")
    cancel.request_stop(source.id)
    source.status = "stopping"
    db.commit()
    return _out(source)


@router.delete("/{source_id}", status_code=204)
def delete_source(source_id: str, db: Session = Depends(get_db), ws: Workspace = Depends(current_workspace)):
    from app import vector_store

    source = _owned(db, source_id, ws)
    cancel.request_stop(source.id)
    vector_store.delete_source(source_id)
    db.delete(source)
    db.commit()
