"""Source in, indexed chunks out.

Runs in a background thread when triggered from the API, because crawling a
hundred-page site takes a minute and the HTTP request should not wait for it.
Status on the source row is how the frontend follows along.

Stopping. A stop request is honoured between pages while crawling and between
batches while embedding. The existing chunks for the source are only replaced at
the very end, after everything new has been embedded, so stopping part-way never
leaves a source half-indexed: it keeps whatever it had before.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone

import numpy as np
from sqlalchemy.orm import Session

from app import embeddings, vector_store
from app.config import settings
from app.db import SessionLocal
from app.ingest import cancel, chunker, crawler
from app.models import Chunk, Source, Workspace

log = logging.getLogger(__name__)

EMBED_BATCH = 64


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _set_status(db: Session, source: Source, status: str, error: str | None = None) -> None:
    source.status = status
    source.error = error
    db.commit()


def chunk_settings(db: Session, workspace_id: str) -> tuple[int, int, int]:
    """(target words, overlap words, max pages) for a workspace, falling back to config."""
    ws = db.get(Workspace, workspace_id)
    target = (ws.chunk_target_words if ws else None) or settings.chunk_target_words
    overlap = ws.chunk_overlap_words if ws and ws.chunk_overlap_words is not None else settings.chunk_overlap_words
    pages = (ws.crawl_max_pages if ws else None) or settings.crawl_max_pages
    return target, overlap, pages


def _finish_stopped(db: Session, source: Source, previous_pages: int) -> None:
    db.refresh(source)
    # Keep the previous index if there was one; it was never touched. The page
    # count was used as live crawl progress, so put the real figure back.
    source.page_count = previous_pages if source.chunk_count else source.page_count
    if source.chunk_count:
        _set_status(db, source, "ready", "Stopped before finishing. The previous index is still in use.")
    else:
        _set_status(db, source, "stopped", "Stopped before finishing. Reindex to start again.")
    log.info("Ingestion of %s stopped by request", source.id)


def ingest_source(source_id: str) -> None:
    """Full pipeline for one source. Safe to call in a thread."""
    db = SessionLocal()
    try:
        source = db.get(Source, source_id)
        if source is None:
            log.error("No source %s", source_id)
            return

        target, overlap, max_pages = chunk_settings(db, source.workspace_id)
        previous_pages = source.page_count

        try:
            cancel.check(source.id)
            if source.kind == "website":
                raw_chunks, page_count = _from_website(db, source, target, overlap, max_pages)
            else:
                raw_chunks, page_count = _from_file(source, target, overlap)
            cancel.check(source.id)

            if not raw_chunks:
                _set_status(
                    db,
                    source,
                    "failed",
                    "Nothing readable was found. If this is a website, its content may be "
                    "rendered by JavaScript, which this crawler does not execute.",
                )
                return

            _set_status(db, source, "indexing")
            texts = [c.text for c in raw_chunks]
            vectors = _embed_stoppable(source.id, texts)
        except cancel.Stopped:
            _finish_stopped(db, source, previous_pages)
            return
        except Exception as exc:  # noqa: BLE001 - surfaced to the user, not swallowed
            log.exception("Ingestion failed for %s", source_id)
            if source.chunk_count:
                source.page_count = previous_pages
            _set_status(db, source, "failed", str(exc)[:500])
            return

        # ---- replace: from here on the work is quick and not interruptible ----
        db.query(Chunk).filter(Chunk.source_id == source.id).delete()
        vector_store.delete_source(source.id)
        db.commit()

        ids, metadatas = [], []
        for raw in raw_chunks:
            chunk_id = new_id("chk")
            ids.append(chunk_id)
            metadatas.append(
                {
                    "source_id": source.id,
                    "workspace_id": source.workspace_id,
                    "organization_id": source.organization_id,
                    "source_label": source.label,
                    "heading_path": raw.heading_path,
                    "url": raw.url or source.location,
                }
            )
            db.add(
                Chunk(
                    id=chunk_id,
                    organization_id=source.organization_id,
                    source_id=source.id,
                    heading_path=raw.heading_path,
                    url=raw.url,
                    text=raw.text,
                    word_count=raw.word_count,
                )
            )

        vector_store.upsert(ids, vectors, metadatas, texts)

        source.page_count = page_count
        source.chunk_count = len(ids)
        source.last_indexed_at = datetime.now(timezone.utc)
        source.content_hash = hashlib.sha256("".join(texts).encode()).hexdigest()[:16]
        source.status = "ready"
        source.error = None
        db.commit()
        log.info(
            "Indexed %s: %d pages, %d chunks (target %d words, overlap %d)",
            source.label, page_count, len(ids), target, overlap,
        )
    finally:
        cancel.clear(source_id)
        db.close()


def _embed_stoppable(source_id: str, texts: list[str]) -> np.ndarray:
    parts = []
    for start in range(0, len(texts), EMBED_BATCH):
        cancel.check(source_id)
        parts.append(embeddings.embed(texts[start : start + EMBED_BATCH]))
    return np.concatenate(parts) if parts else embeddings.embed([])


def _from_website(
    db: Session, source: Source, target: int, overlap: int, max_pages: int
) -> tuple[list[chunker.RawChunk], int]:
    _set_status(db, source, "crawling")

    def progress(n: int) -> None:
        # Page count doubles as a live progress figure while crawling.
        source.page_count = n
        db.commit()

    pages = crawler.crawl(
        source.location,
        max_pages=max_pages,
        should_stop=lambda: cancel.is_requested(source.id),
        on_page=progress,
    )
    cancel.check(source.id)

    chunks: list[chunker.RawChunk] = []
    for page in pages:
        soup = crawler.extract_main_text(page.html)
        sections = chunker.sections_from_html(soup)
        chunks.extend(chunker.chunk_sections(sections, url=page.url, target=target, overlap=overlap))
    return chunks, len(pages)


def _from_file(source: Source, target: int, overlap: int) -> tuple[list[chunker.RawChunk], int]:
    path = source.location
    if source.kind == "pdf":
        text = chunker.parse_pdf(path)
    elif source.kind == "docx":
        text = chunker.parse_docx(path)
    else:
        text = chunker.parse_text(path)

    sections = chunker.sections_from_plain(text, source.label)
    return chunker.chunk_sections(sections, url=None, target=target, overlap=overlap), 1
