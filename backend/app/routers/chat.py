from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Workspace
from app.rag import engine
from app.schemas import ChatRequest, CitationOut, MessageOut
from app.workspaces import current_workspace

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=MessageOut)
def chat(payload: ChatRequest, db: Session = Depends(get_db), ws: Workspace = Depends(current_workspace)):
    message = engine.answer(db, payload.question, payload.session_id, workspace_id=ws.id)
    return MessageOut(
        id=message.id,
        role=message.role,
        text=message.text,
        createdAt=message.created_at,
        confidence=message.confidence,
        citations=[CitationOut(**c) for c in getattr(message, "citations_payload", [])],
    )
