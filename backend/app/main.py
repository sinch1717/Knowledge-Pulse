from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.migrate import upgrade
from app.routers import auth, chat, insights, research, sources, workspaces

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("knowledgepulse")


def _backfill_vectors() -> None:
    """Tag chunks indexed before workspaces or organisations with both."""
    from app import vector_store
    from app.db import SessionLocal
    from app.models import Workspace
    from app.tenant import default_workspace_id

    db = SessionLocal()
    try:
        owners = {w.id: w.organization_id for w in db.query(Workspace).all()}
    finally:
        db.close()
    vector_store.backfill_tenancy(default_workspace_id, owners, settings.default_organization_id)


def _ensure_demo_user() -> None:
    from app.auth import ensure_demo_user
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        ensure_demo_user(db)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_: FastAPI):
    upgrade()
    log.info("Database ready at %s", settings.database_url)
    try:
        _backfill_vectors()
    except Exception as exc:  # noqa: BLE001 - the API should still start
        log.warning("Could not tag existing chunks with a workspace: %s", exc)
    _ensure_demo_user()
    log.info("Language model provider: %s", settings.llm_provider)
    yield


app = FastAPI(
    title="KnowledgePulse",
    version="0.1.0",
    description=(
        "A support assistant that answers from an organisation's own documents, and an "
        "analytics layer that reads the resulting conversations and reports what customers "
        "are stuck on."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(workspaces.router)
app.include_router(sources.router)
app.include_router(chat.router)
app.include_router(insights.router)
app.include_router(research.router)


# Public, no sign-in: infrastructure checks only, no tenant data.
@app.get("/api/health")
def health():
    from app import vector_store

    try:
        indexed = vector_store.count()
    except Exception as exc:  # noqa: BLE001
        indexed = -1
        log.warning("Vector store not reachable: %s", exc)
    return {"status": "ok", "indexedChunks": indexed, "llmProvider": settings.llm_provider}
