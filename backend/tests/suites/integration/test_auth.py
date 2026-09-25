"""Sign-in: accounts, sessions, sign-out, and how the organisation is derived."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app import auth
from app.config import settings
from app.models import AuthSession, User


def test_demo_account_exists_after_start_up_and_belongs_to_the_default_organisation(client, db):
    """Start-up creates the demo user from settings, in org_default."""
    resp = client.post("/api/auth/login", json={"email": settings.demo_user_email,
                                                "password": settings.demo_user_password})
    assert resp.status_code == 200
    user = resp.json()["user"]
    assert user["organizationId"] == settings.default_organization_id
    assert user["name"] == settings.demo_user_name


def test_login_returns_a_token_the_api_accepts(tenant):
    """The token from /login works on /me and on business routes."""
    me = tenant.get("/api/auth/me").json()
    assert me == {"id": me["id"], "email": tenant.email, "name": f"User of {tenant.org}",
                  "organizationId": tenant.org}
    assert tenant.get("/api/sources").status_code == 200


def test_email_is_case_insensitive(tenant):
    resp = tenant.client.post("/api/auth/login", json={"email": tenant.email.upper(), "password": tenant.password})
    assert resp.status_code == 200


@pytest.mark.parametrize("email_ok,password_ok", [(True, False), (False, True), (False, False)])
def test_wrong_credentials_get_the_same_answer(tenant, email_ok, password_ok):
    """Wrong email and wrong password are indistinguishable to the caller."""
    resp = tenant.client.post("/api/auth/login", json={
        "email": tenant.email if email_ok else "nobody@test.local",
        "password": tenant.password if password_ok else "wrong-password",
    })
    assert resp.status_code == 401 and resp.json()["detail"] == "Email or password is incorrect."


def test_logout_ends_the_session_on_the_server(tenant):
    """After sign-out the same token is refused, even if the browser kept it."""
    assert tenant.post("/api/auth/logout").status_code == 204
    resp = tenant.get("/api/sources")
    assert resp.status_code == 401 and "Sign in again" in resp.json()["detail"]
    assert tenant.get("/api/auth/me").status_code == 401
    assert tenant.client.post("/api/auth/logout", headers=tenant.headers()).status_code == 204  # idempotent


def test_other_sessions_survive_a_logout(tenant):
    """Signing out one browser leaves the user's other sessions alone."""
    second = tenant.sign_in()
    tenant.post("/api/auth/logout")
    assert tenant.client.get("/api/sources", headers={"Authorization": f"Bearer {second}"}).status_code == 200


def test_expired_sessions_are_refused_and_removed(tenant, db):
    """A session past its expiry gets 401 and its row is deleted."""
    session = db.get(AuthSession, auth._token_hash(tenant.token))
    session.expires_at = session.expires_at - timedelta(hours=settings.session_ttl_hours + 1)
    db.commit()
    assert tenant.get("/api/sources").status_code == 401
    db.expire_all()
    assert db.get(AuthSession, auth._token_hash(tenant.token)) is None


def test_session_lifetime_follows_the_setting(tenant):
    """expiresAt is session_ttl_hours after sign-in."""
    from datetime import datetime

    resp = tenant.client.post("/api/auth/login", json={"email": tenant.email, "password": tenant.password}).json()
    expires = datetime.fromisoformat(resp["expiresAt"])
    lifetime = expires - datetime.utcnow()
    assert timedelta(hours=settings.session_ttl_hours - 1) < lifetime <= timedelta(hours=settings.session_ttl_hours)


def test_tokens_are_not_stored_in_clear(tenant, db):
    """The database holds a hash of the token, never the token itself."""
    rows = db.query(AuthSession).all()
    assert all(r.id != tenant.token for r in rows)
    assert db.get(AuthSession, auth._token_hash(tenant.token)) is not None


def test_passwords_are_hashed_with_a_salt(db):
    """Same password, two users, two different hashes; neither contains the password."""
    a = auth.create_or_update_user(db, "salt-a@test.local", "same-password", "A", "org_salt")
    b = auth.create_or_update_user(db, "salt-b@test.local", "same-password", "B", "org_salt")
    assert a.password_hash != b.password_hash
    assert "same-password" not in a.password_hash
    assert auth.verify_password("same-password", a.password_hash)
    assert not auth.verify_password("other", a.password_hash)


def test_malformed_authorization_headers_are_refused(client):
    for value in ("Bearer", "Bearer   ", "Basic abc", "token-without-scheme"):
        assert client.get("/api/sources", headers={"Authorization": value}).status_code == 401


def test_changing_the_demo_password_setting_takes_effect_on_restart(db, monkeypatch):
    """ensure_demo_user resets the stored password when the setting changes."""
    monkeypatch.setattr(settings, "demo_user_password", "rotated-password")
    auth.ensure_demo_user(db)
    user = db.query(User).filter(User.email == settings.demo_user_email).one()
    assert auth.verify_password("rotated-password", user.password_hash)
    monkeypatch.undo()
    auth.ensure_demo_user(db)


def test_create_user_script(tmp_path, monkeypatch, db, client):
    """scripts/create_user.py creates an account that can sign in to its organisation."""
    import runpy
    import sys
    from pathlib import Path

    script = Path(__file__).resolve().parents[3] / "scripts" / "create_user.py"
    monkeypatch.setattr(sys, "argv", ["create_user.py", "--email", "new@test.local", "--name", "New",
                                      "--organization-id", "org_script_made", "--password", "long-enough"])
    runpy.run_path(str(script), run_name="__main__")
    resp = client.post("/api/auth/login", json={"email": "new@test.local", "password": "long-enough"})
    assert resp.json()["user"]["organizationId"] == "org_script_made"
    token = resp.json()["token"]
    workspaces = client.get("/api/workspaces", headers={"Authorization": f"Bearer {token}"}).json()
    assert [w["isDefault"] for w in workspaces] == [True]
