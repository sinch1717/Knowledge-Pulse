"""Ingestion: crawler, parsers, chunker, embedder, SQL and Chroma working together."""

from __future__ import annotations

import pytest

from app import vector_store
from app.ingest import crawler
from app.models import Chunk, Source


def _chunks(db, source_id):
    return db.query(Chunk).filter(Chunk.source_id == source_id).all()


def test_crawler_follows_internal_links_and_skips_files_logins_and_other_sites(site):
    """The crawl stays inside the site and skips downloads and login pages."""
    pages = {p.url.replace(site, "") for p in crawler.crawl(f"{site}/docs/")}
    for expected in ("/docs/", "/docs/invoices.html", "/docs/team.html", "/docs/settings.html"):
        assert expected in pages
    assert not any(p.endswith(".pdf") for p in pages)
    assert not any("/login" in p for p in pages)
    assert not any("example.com" in p for p in pages)


def test_crawler_respects_page_limit(site):
    """max_pages caps the crawl."""
    assert len(crawler.crawl(f"{site}/docs/", max_pages=3)) == 3


def test_website_source_indexes_into_sql_and_chroma_consistently(indexed, db):
    """Chunk rows, vectors and the source's counters agree after a crawl."""
    source = indexed.site_source
    rows = _chunks(db, source["id"])
    assert source["pageCount"] >= 7
    assert source["chunkCount"] == len(rows) > 0
    assert source["contentHash"] and source["lastIndexedAt"]
    assert vector_store.count(indexed.default_workspace, indexed.org) == len(rows)

    stored = vector_store._get_collection().get(ids=[r.id for r in rows], include=["metadatas"])
    for meta in stored["metadatas"]:
        assert meta["source_id"] == source["id"]
        assert meta["workspace_id"] == indexed.default_workspace
        assert meta["organization_id"] == indexed.org
        assert meta["heading_path"] and meta["url"].startswith("http")
    assert all(r.organization_id == indexed.org for r in rows)


def test_navigation_and_footer_boilerplate_is_not_indexed(indexed, db):
    """Header, nav, aside and footer text never reaches the index."""
    text = " ".join(r.text for r in _chunks(db, indexed.site_source["id"]))
    for boilerplate in ("Newsletter signup", "Careers", "Pricing", "Docs home"):
        assert boilerplate not in text
    assert "edit an invoice after sending" in text


def test_headings_become_heading_paths(indexed, db):
    """Each chunk keeps the path of headings above it."""
    paths = {r.heading_path for r in _chunks(db, indexed.site_source["id"])}
    assert "Invoices › Editing an invoice after sending" in paths
    assert "Invoices › Sending invoices by email › Invoice reminders" in paths


def test_javascript_only_page_fails_with_an_explanation(tenant, site):
    """A page with no server-rendered text fails loudly instead of indexing nothing."""
    source = tenant.add_website(f"{site}/docs/app.html")
    assert source["status"] == "failed"
    assert "JavaScript" in source["error"]


def test_unreachable_site_fails_cleanly(tenant):
    """A site that cannot be reached ends in failed, not stuck in crawling."""
    source = tenant.add_website("http://127.0.0.1:9/docs/")
    assert source["status"] == "failed"


@pytest.mark.parametrize("kind", ["pdf", "docx", "txt", "md"])
def test_uploaded_documents_are_parsed_chunked_and_searchable(tenant, tmp_path, kind):
    """PDF, DOCX, TXT and MD uploads index and can be cited in chat."""
    text = "Late fees. A late fee of two percent is added to overdue invoices after thirty days."
    path = tmp_path / f"policy.{kind}"
    if kind == "pdf":
        import fitz

        doc = fitz.open()
        doc.new_page().insert_text((72, 72), text)
        doc.save(path)
    elif kind == "docx":
        import docx

        document = docx.Document()
        document.add_paragraph(text)
        document.save(path)
    else:
        path.write_text(text)

    with path.open("rb") as fh:
        resp = tenant.post("/api/sources/upload", files={"file": (path.name, fh)}, data={"label": f"Policy {kind}"})
    assert resp.status_code == 201, resp.text
    source = tenant.source(resp.json()["id"])
    assert source["status"] == "ready" and source["chunkCount"] >= 1
    answer = tenant.ask("late fee on overdue invoices")
    assert any(c["sourceLabel"] == f"Policy {kind}" for c in answer["citations"])


def test_upload_rejects_unsupported_file_types(tenant):
    """Only PDF, DOCX, TXT and MD are accepted."""
    resp = tenant.post("/api/sources/upload", files={"file": ("tool.exe", b"MZ")})
    assert resp.status_code == 400


def test_reindex_replaces_chunks_instead_of_adding_to_them(indexed, db):
    """Reindexing leaves exactly one copy of the site in SQL and in Chroma."""
    source_id = indexed.site_source["id"]
    before = {r.id for r in _chunks(db, source_id)}
    assert indexed.post(f"/api/sources/{source_id}/reindex").status_code == 200
    db.expire_all()
    after = {r.id for r in _chunks(db, source_id)}
    assert len(after) == len(before) and not (after & before)
    assert vector_store.count(indexed.default_workspace, indexed.org) == len(after)


def test_stopping_a_reindex_keeps_the_previous_index(indexed, db, monkeypatch):
    """A stop part-way through never leaves a source half-indexed."""
    from app.ingest import cancel, pipeline

    source_id = indexed.site_source["id"]
    before = {r.id for r in _chunks(db, source_id)}
    real_crawl = crawler.crawl

    def crawl_then_stop(url, **kw):
        cancel.request_stop(source_id)  # as if the user pressed Stop during the crawl
        return real_crawl(url, **kw)

    monkeypatch.setattr(pipeline.crawler, "crawl", crawl_then_stop)
    indexed.post(f"/api/sources/{source_id}/reindex")
    source = indexed.source(source_id)
    db.expire_all()
    assert source["status"] == "ready"
    assert "Stopped" in source["error"]
    assert {r.id for r in _chunks(db, source_id)} == before
    assert source["pageCount"] == indexed.site_source["pageCount"]


def test_stopping_a_first_index_leaves_the_source_stopped(tenant, site, monkeypatch):
    """A source stopped before it was ever indexed reads as stopped, with no chunks."""
    from app.ingest import cancel, pipeline

    real_crawl = crawler.crawl

    def crawl_then_stop(url, **kw):
        cancel.request_stop(kw_source["id"])
        return real_crawl(url, **kw)

    kw_source = {}
    real_add = pipeline.ingest_source

    def capture(source_id):
        kw_source["id"] = source_id
        return real_add(source_id)

    monkeypatch.setattr(pipeline.crawler, "crawl", crawl_then_stop)
    import app.routers.sources as sources_router

    monkeypatch.setattr(sources_router, "ingest_source", capture)
    source = tenant.add_website(f"{site}/docs/team.html")
    assert source["status"] == "stopped" and source["chunkCount"] == 0


def test_stop_is_refused_when_nothing_is_running(indexed):
    """Stop on an idle source is a 409, not a silent no-op."""
    assert indexed.post(f"/api/sources/{indexed.site_source['id']}/stop").status_code == 409


def test_deleting_a_source_removes_its_chunks_vectors_and_citations(indexed, db):
    """After delete, nothing of the source can be retrieved."""
    source_id = indexed.site_source["id"]
    assert indexed.delete(f"/api/sources/{source_id}").status_code == 204
    db.expire_all()
    assert db.get(Source, source_id) is None
    assert _chunks(db, source_id) == []
    assert vector_store.count(indexed.default_workspace, indexed.org) == 0
    assert indexed.ask("edit an invoice after sending")["citations"] == []
