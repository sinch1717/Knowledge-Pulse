"""Workspaces inside one organisation: lifecycle, settings, and separation."""

from __future__ import annotations

import pytest

from app import vector_store
from app.models import Chunk, Conversation, Source


def test_workspace_lifecycle(tenant):
    """Create, list, rename and delete a workspace."""
    created = tenant.post("/api/workspaces", json={"name": "  Mobile app docs  ", "description": "iOS"}).json()
    assert created["name"] == "Mobile app docs" and not created["isDefault"] and created["usesDefaults"]
    listed = tenant.get("/api/workspaces").json()
    assert listed[0]["isDefault"] and created["id"] in [w["id"] for w in listed]

    renamed = tenant.patch(f"/api/workspaces/{created['id']}", json={"name": "Mobile"}).json()
    assert renamed["name"] == "Mobile" and renamed["description"] == "iOS"
    assert tenant.delete(f"/api/workspaces/{created['id']}").status_code == 204
    assert created["id"] not in [w["id"] for w in tenant.get("/api/workspaces").json()]


@pytest.mark.parametrize(
    "payload",
    [
        {"name": ""},
        {"name": "x", "chunkTargetWords": 10},
        {"name": "x", "chunkTargetWords": 5000},
        {"name": "x", "chunkTargetWords": 100, "chunkOverlapWords": 100},
        {"name": "x", "crawlMaxPages": 0},
    ],
)
def test_invalid_workspace_settings_are_rejected(tenant, payload):
    """Out-of-range chunk settings are refused with 400."""
    assert tenant.post("/api/workspaces", json=payload).status_code == 400


def test_default_workspace_cannot_be_deleted(tenant):
    """Every organisation always keeps one workspace."""
    assert tenant.delete(f"/api/workspaces/{tenant.default_workspace}").status_code == 400


def test_workspaces_do_not_see_each_others_sources_or_chunks(indexed):
    """A second workspace starts empty and cannot retrieve the first one's chunks."""
    other = indexed.post("/api/workspaces", json={"name": "Second"}).json()["id"]
    assert indexed.get("/api/sources", workspace=other).json() == []
    reply = indexed.post("/api/chat", workspace=other, json={"question": "edit an invoice", "session_id": "s"}).json()
    assert reply["citations"] == []


def test_chunk_settings_change_how_a_workspace_indexes(indexed, site, db):
    """Smaller chunk size on a workspace gives more, smaller chunks for the same page."""
    small = indexed.post(
        "/api/workspaces", json={"name": "Small chunks", "chunkTargetWords": 60, "chunkOverlapWords": 10}
    ).json()
    assert not small["usesDefaults"] and small["chunkTargetWords"] == 60
    url = f"{site}/docs/settings.html"
    default_src = indexed.post("/api/sources", json={"kind": "website", "location": url}).json()["id"]
    small_src = indexed.post("/api/sources", workspace=small["id"], json={"kind": "website", "location": url}).json()["id"]
    words = lambda sid: [c.word_count for c in db.query(Chunk).filter(Chunk.source_id == sid)]  # noqa: E731
    assert len(words(small_src)) > len(words(default_src))
    assert max(words(small_src)) <= 60


def test_deleting_a_workspace_deletes_everything_in_it(indexed, db):
    """Sources, chunks, vectors and conversations go with the workspace."""
    ws = indexed.post("/api/workspaces", json={"name": "Temporary"}).json()["id"]
    src = indexed.post("/api/sources", workspace=ws, json={"kind": "website", "location": indexed.site_source["location"]}).json()["id"]
    indexed.post("/api/chat", workspace=ws, json={"question": "refunds", "session_id": "s_tmp"})
    assert vector_store.count(ws, indexed.org) > 0

    assert indexed.delete(f"/api/workspaces/{ws}").status_code == 204
    db.expire_all()
    assert db.get(Source, src) is None
    assert db.query(Chunk).filter(Chunk.source_id == src).count() == 0
    assert db.query(Conversation).filter(Conversation.workspace_id == ws).count() == 0
    assert vector_store.count(ws, indexed.org) == 0
    # The default workspace is untouched.
    assert indexed.source(indexed.site_source["id"])["status"] == "ready"


def test_unknown_workspace_header_is_a_404(tenant):
    """A deleted or mistyped workspace id gets a clear 404."""
    resp = tenant.get("/api/sources", workspace="ws_does_not_exist")
    assert resp.status_code == 404 and "pick another" in resp.json()["detail"]
