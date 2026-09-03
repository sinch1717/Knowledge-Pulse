from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import OrgProfile


router = APIRouter(prefix="/api/org-profile", tags=["org-profile"])


class OrgProfileOut(BaseModel):
    name: str
    description: str
    industry: str
    voice_description: str


class OrgProfileUpdate(BaseModel):
    name: str
    description: str = ""
    industry: str = ""
    voice_description: str = ""


def get_or_create_profile(db: Session) -> OrgProfile:
    profile = db.get(OrgProfile, 1)

    if profile is None:
        profile = OrgProfile(
            id=1,
            name="KnowledgePulse",
            description="",
            industry="",
            voice_description="Professional, concise, friendly and helpful.",
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)

    return profile


@router.get("", response_model=OrgProfileOut)
def get_profile(db: Session = Depends(get_db)):
    profile = get_or_create_profile(db)
    return profile


@router.put("", response_model=OrgProfileOut)
def update_profile(
    payload: OrgProfileUpdate,
    db: Session = Depends(get_db),
):
    profile = get_or_create_profile(db)

    profile.name = payload.name
    profile.description = payload.description
    profile.industry = payload.industry
    profile.voice_description = payload.voice_description

    db.commit()
    db.refresh(profile)

    return profile
