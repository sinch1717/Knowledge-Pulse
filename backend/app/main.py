from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import create_tables
from app.routers import chat, insights, sources,org_profile

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("knowledgepulse")


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_tables()
    log.info("Database ready at %s", settings.database_url)
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

app.include_router(sources.router)
app.include_router(chat.router)
app.include_router(insights.router)
app.include_router(org_profile.router)


@app.get("/api/health")
def health():
    from app import vector_store

    try:
        indexed = vector_store.count()
    except Exception as exc:  # noqa: BLE001
        indexed = -1
        log.warning("Vector store not reachable: %s", exc)
    return {"status": "ok", "indexedChunks": indexed, "llmProvider": settings.llm_provider}
