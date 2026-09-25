"""Sign-in for local development and demos.

Deliberately small and dependency-free:

- Passwords: PBKDF2-HMAC-SHA256 from the standard library, a random salt per
  user, stored as "pbkdf2_sha256$<iterations>$<salt>$<hash>".
- Sessions: a random 256-bit bearer token handed to the browser once. Only its
  SHA-256 is stored, so a copy of the database cannot be used to sign in. Signing
  out deletes the row, so a token stops working immediately.
- The browser sends the token as "Authorization: Bearer <token>". The
  organisation is read from the session's user; the frontend never names it.

Not included, and needed before this faces the public internet: rate limiting on
sign-in, password reset, and account management beyond scripts/create_user.py.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import uuid
from datetime import timedelta

from fastapi import Header, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.models import AuthSession, User, utcnow_naive

log = logging.getLogger(__name__)

PBKDF2_ITERATIONS = 240_000
DEFAULT_DEMO_PASSWORD = "knowledgepulse"


# ---- passwords ------------------------------------------------------------------

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS).hex()
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt, digest = stored.split("$")
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iterations)).hex()
    return hmac.compare_digest(candidate, digest)


def normalise_email(email: str) -> str:
    return email.strip().lower()


# ---- users ------------------------------------------------------------------------

def create_or_update_user(
    db: Session, email: str, password: str, name: str, organization_id: str
) -> User:
    """Create a user, or reset an existing one's password, name and organisation."""
    email = normalise_email(email)
    user = db.query(User).filter(User.email == email).one_or_none()
    if user is None:
        user = User(id=f"usr_{uuid.uuid4().hex[:12]}", email=email)
        db.add(user)
    user.name = name
    user.organization_id = organization_id
    if not user.password_hash or not verify_password(password, user.password_hash):
        user.password_hash = hash_password(password)
    db.commit()
    return user


def ensure_demo_user(db: Session) -> None:
    """Create the demo account from settings, or bring its password up to date."""
    if not settings.demo_user_password:
        return
    create_or_update_user(
        db,
        settings.demo_user_email,
        settings.demo_user_password,
        settings.demo_user_name,
        settings.default_organization_id,
    )
    if settings.demo_user_password == DEFAULT_DEMO_PASSWORD:
        log.warning(
            "Demo account %s is using the default password. Set DEMO_USER_PASSWORD "
            "before exposing this deployment.",
            settings.demo_user_email,
        )


def authenticate(db: Session, email: str, password: str) -> User | None:
    user = db.query(User).filter(User.email == normalise_email(email)).one_or_none()
    if user is None:
        # Spend the same time as a real check, so response time does not reveal
        # which emails have accounts.
        verify_password(password, hash_password("timing-equaliser"))
        return None
    return user if verify_password(password, user.password_hash) else None


# ---- sessions -------------------------------------------------------------------------

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def start_session(db: Session, user: User) -> tuple[str, AuthSession]:
    """Create a session and return the token, which is never stored in clear."""
    now = utcnow_naive()
    db.query(AuthSession).filter(AuthSession.expires_at < now).delete()  # tidy as we go
    token = secrets.token_urlsafe(32)
    session = AuthSession(
        id=_token_hash(token),
        user_id=user.id,
        created_at=now,
        expires_at=now + timedelta(hours=settings.session_ttl_hours),
    )
    db.add(session)
    db.commit()
    return token, session


def session_for_token(db: Session, token: str) -> AuthSession | None:
    session = db.get(AuthSession, _token_hash(token))
    if session is None:
        return None
    if session.expires_at <= utcnow_naive():
        db.delete(session)
        db.commit()
        return None
    return session


def end_session(db: Session, token: str) -> None:
    session = db.get(AuthSession, _token_hash(token))
    if session is not None:
        db.delete(session)
        db.commit()


def bearer_token(authorization: str | None = Header(default=None)) -> str | None:
    """The token from "Authorization: Bearer <token>", or None."""
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def require_session(db: Session, token: str | None) -> AuthSession:
    if not token:
        raise HTTPException(401, "Sign in to continue.", headers={"WWW-Authenticate": "Bearer"})
    session = session_for_token(db, token)
    if session is None:
        raise HTTPException(
            401, "Your session has ended. Sign in again.", headers={"WWW-Authenticate": "Bearer"}
        )
    return session
