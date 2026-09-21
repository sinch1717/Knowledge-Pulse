"""Source in, indexed chunks out.

Runs in a background thread when triggered from the API, because crawling a
hundred-page site takes a minute and the HTTP request should not wait for it.
Status on the source row is how the frontend follows along.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app import embeddings, vector_store
from app.db import SessionLocal
from app.ingest import chunker, crawler
from app.models import Chunk, Source

log = logging.getLogger(__name__)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _set_status(db: Session, source: Source, status: str, error: str | None = None) -> None:
    source.status = status
    source.error = error
    db.commit()


def ingest_source(source_id: str) -> None:
    """Full pipeline for one source. Safe to call in a thread."""
    db = SessionLocal()
    try:
        source = db.get(Source, source_id)
        if source is None:
            log.error("No source %s", source_id)
            return

        try:
            if source.kind == "website":
                raw_chunks, page_count = _from_website(source)
            else:
                raw_chunks, page_count = _from_file(source)
        except Exception as exc:  # noqa: BLE001 - surfaced to the user, not swallowed
            log.exception("Ingestion failed for %s", source_id)
            _set_status(db, source, "failed", str(exc)[:500])
            return

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

        # Replace rather than append, so re-indexing does not duplicate content.
        db.query(Chunk).filter(Chunk.source_id == source.id).delete()
        vector_store.delete_source(source.id)
        db.commit()

        texts = [c.text for c in raw_chunks]
        vectors = embeddings.embed(texts)

        ids, metadatas = [], []
        for raw, _ in zip(raw_chunks, vectors):
            chunk_id = new_id("chk")
            ids.append(chunk_id)
            metadatas.append(
                {
                    "source_id": source.id,
                    "source_label": source.label,
                    "heading_path": raw.heading_path,
                    "url": raw.url or source.location,
                }
            )
            db.add(
                Chunk(
                    id=chunk_id,
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
        log.info("Indexed %s: %d pages, %d chunks", source.label, page_count, len(ids))
    finally:
        db.close()


def _from_website(source: Source) -> tuple[list[chunker.RawChunk], int]:
    db = SessionLocal()
    try:
        live = db.get(Source, source.id)
        if live:
            live.status = "crawling"
            db.commit()
    finally:
        db.close()

    pages = crawler.crawl(source.location)
    chunks: list[chunker.RawChunk] = []
    for page in pages:
        soup = crawler.extract_main_text(page.html)
        sections = chunker.sections_from_html(soup)
        chunks.extend(chunker.chunk_sections(sections, url=page.url))
    return chunks, len(pages)


def _from_file(source: Source) -> tuple[list[chunker.RawChunk], int]:
    path = source.location
    if source.kind == "pdf":
        text = chunker.parse_pdf(path)
    elif source.kind == "docx":
        text = chunker.parse_docx(path)
    else:
        text = chunker.parse_text(path)

    sections = chunker.sections_from_plain(text, source.label)
    return chunker.chunk_sections(sections, url=None), 1
