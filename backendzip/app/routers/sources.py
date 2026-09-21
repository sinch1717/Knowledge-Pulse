from __future__ import annotations

import os
import shutil
import uuid
from urllib.parse import urlparse

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.ingest.pipeline import ingest_source
from app.models import Source
from app.schemas import SourceCreate, SourceOut

router = APIRouter(prefix="/api/sources", tags=["sources"])

EXTENSION_KIND = {".pdf": "pdf", ".docx": "docx", ".txt": "text", ".md": "text"}


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


@router.get("", response_model=list[SourceOut])
def list_sources(db: Session = Depends(get_db)):
    rows = db.query(Source).order_by(Source.created_at.desc()).all()
    return [_out(s) for s in rows]


@router.post("", response_model=SourceOut, status_code=201)
def create_source(payload: SourceCreate, tasks: BackgroundTasks, db: Session = Depends(get_db)):
    if payload.kind == "website" and not payload.location.startswith(("http://", "https://")):
        raise HTTPException(400, "A website source needs a full URL starting with http:// or https://")

    label = payload.label or (
        urlparse(payload.location).netloc or os.path.basename(payload.location) or payload.location
    )
    source = Source(
        id=f"src_{uuid.uuid4().hex[:10]}",
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
    tasks: BackgroundTasks, file: UploadFile = File(...), db: Session = Depends(get_db)
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
        kind=EXTENSION_KIND[extension],
        label=file.filename or destination,
        location=destination,
        status="queued",
    )
    db.add(source)
    db.commit()

    tasks.add_task(ingest_source, source.id)
    return _out(source)


@router.post("/{source_id}/reindex", response_model=SourceOut)
def reindex(source_id: str, tasks: BackgroundTasks, db: Session = Depends(get_db)):
    source = db.get(Source, source_id)
    if source is None:
        raise HTTPException(404, "No source with that id")
    source.status = "queued"
    source.error = None
    db.commit()
    tasks.add_task(ingest_source, source.id)
    return _out(source)


@router.delete("/{source_id}", status_code=204)
def delete_source(source_id: str, db: Session = Depends(get_db)):
    from app import vector_store

    source = db.get(Source, source_id)
    if source is None:
        raise HTTPException(404, "No source with that id")
    vector_store.delete_source(source_id)
    db.delete(source)
    db.commit()
