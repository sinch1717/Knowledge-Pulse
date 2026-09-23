"""Thin wrapper over the vector store.

Everything the rest of the system does with vectors goes through these four
functions. If Chroma ever needs to become pgvector, this is the only file that
changes.

Note that similarity is returned as cosine similarity in [0, 1]. Chroma hands
back a distance, and getting that conversion wrong would quietly corrupt every
confidence score in the system, so it happens once, here.
"""

from __future__ import annotations

import logging
import os

from app.config import settings

log = logging.getLogger(__name__)

COLLECTION = "knowledge_chunks"
_client = None
_collection = None


def _get_collection():
    global _client, _collection
    if _collection is None:
        # Must be set before chromadb is imported; passing it in Settings alone
        # does not stop the client's own start-up event.
        os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")

        import chromadb
        from chromadb.config import Settings as ChromaSettings

        os.makedirs(settings.chroma_path, exist_ok=True)
        # Telemetry is off: it is noisy, it errors on some versions, and there is
        # no reason for a project like this to phone home.
        _client = chromadb.PersistentClient(
            path=settings.chroma_path,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        _collection = _client.get_or_create_collection(
            name=COLLECTION, metadata={"hnsw:space": "cosine"}
        )
    return _collection


def upsert(chunk_ids: list[str], vectors, metadatas: list[dict], documents: list[str]) -> None:
    if not chunk_ids:
        return
    _get_collection().upsert(
        ids=chunk_ids,
        embeddings=[v.tolist() for v in vectors],
        metadatas=metadatas,
        documents=documents,
    )


def delete_source(source_id: str) -> None:
    _get_collection().delete(where={"source_id": source_id})


def count(workspace_id: str | None = None) -> int:
    collection = _get_collection()
    if workspace_id is None:
        return collection.count()
    return len(collection.get(where={"workspace_id": workspace_id}, include=[])["ids"])


def backfill_workspace(default_workspace_id: str, batch: int = 500) -> int:
    """Tag chunks indexed before workspaces existed. Returns how many were updated.

    Chroma cannot filter on a missing key, so this reads every metadata once. It
    is cheap at this scale and a no-op after the first run.
    """
    collection = _get_collection()
    total = collection.count()
    updated = 0
    for offset in range(0, total, batch):
        page = collection.get(include=["metadatas"], limit=batch, offset=offset)
        ids, metas = [], []
        for cid, meta in zip(page["ids"], page["metadatas"]):
            meta = dict(meta or {})
            if "workspace_id" not in meta:
                meta["workspace_id"] = default_workspace_id
                ids.append(cid)
                metas.append(meta)
        if ids:
            collection.update(ids=ids, metadatas=metas)
            updated += len(ids)
    if updated:
        log.info("Tagged %d existing chunks with workspace %s", updated, default_workspace_id)
    return updated


def search(vector, top_k: int, workspace_id: str | None = None) -> list[dict]:
    """Return the top-k chunks with cosine similarity in [0, 1], best first.

    With a workspace id, only that workspace's chunks are searched, so one
    profile can never answer from another's sources.
    """
    collection = _get_collection()
    available = count(workspace_id)
    if available == 0:
        return []
    res = collection.query(
        query_embeddings=[vector.tolist()],
        n_results=min(top_k, available),
        where={"workspace_id": workspace_id} if workspace_id else None,
        include=["documents", "metadatas", "distances"],
    )
    hits = []
    for cid, doc, meta, dist in zip(
        res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]
    ):
        # Chroma's cosine distance is 1 - cosine_similarity.
        similarity = max(0.0, min(1.0, 1.0 - float(dist)))
        hits.append({"chunk_id": cid, "text": doc, "meta": meta or {}, "similarity": similarity})
    return hits
