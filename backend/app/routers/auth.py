"""Sign in, sign out, and who am I.

The only routes that work without a session (besides health and research).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app import auth
from app.db import get_db
from app.models import User
from app.schemas import LoginRequest, SessionOut, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _user_out(user: User) -> UserOut:
    return UserOut(id=user.id, email=user.email, name=user.name, organizationId=user.organization_id)


@router.post("/login", response_model=SessionOut)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = auth.authenticate(db, payload.email, payload.password)
    if user is None:
        raise HTTPException(401, "Email or password is incorrect.")
    token, session = auth.start_session(db, user)
    return SessionOut(token=token, expiresAt=session.expires_at, user=_user_out(user))


@router.get("/me", response_model=UserOut)
def me(token: str | None = Depends(auth.bearer_token), db: Session = Depends(get_db)):
    return _user_out(auth.require_session(db, token).user)


@router.post("/logout", status_code=204)
def logout(token: str | None = Depends(auth.bearer_token), db: Session = Depends(get_db)):
    # Signing out an already-ended session is not an error: the browser just
    # wants to be signed out.
    if token:
        auth.end_session(db, token)
    return Response(status_code=204)
