from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.rag import engine
from app.schemas import ChatRequest, CitationOut, MessageOut

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=MessageOut)
def chat(payload: ChatRequest, db: Session = Depends(get_db)):
    message = engine.answer(db, payload.question, payload.session_id)
    return MessageOut(
        id=message.id,
        role=message.role,
        text=message.text,
        createdAt=message.created_at,
        confidence=message.confidence,
        citations=[CitationOut(**c) for c in getattr(message, "citations_payload", [])],
    )
