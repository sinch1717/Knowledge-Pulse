"""Acceptance: signing in and out, and conversations that persist."""

from __future__ import annotations

import pytest

req = pytest.mark.req


@req("AUTH1")
def test_auth1_sign_in_with_email_and_password(tenant):
    """Correct credentials give a session naming the user and organisation; wrong ones are refused vaguely."""
    ok = tenant.client.post("/api/auth/login", json={"email": tenant.email, "password": tenant.password})
    assert ok.status_code == 200
    body = ok.json()
    assert body["token"] and body["expiresAt"] and body["user"]["organizationId"] == tenant.org
    bad = tenant.client.post("/api/auth/login", json={"email": tenant.email, "password": "nope"})
    assert bad.status_code == 401 and "Email or password" in bad.json()["detail"]


@req("AUTH2")
def test_auth2_a_session_keeps_working_across_requests_until_it_ends(tenant):
    """The same token works for every later request, as it does after a page reload."""
    for _ in range(3):
        assert tenant.get("/api/auth/me").status_code == 200
        assert tenant.get("/api/workspaces").status_code == 200


@req("AUTH3")
def test_auth3_signing_out_ends_the_session_immediately(tenant):
    """After sign-out the old token is refused everywhere."""
    tenant.post("/api/auth/logout")
    for path in ("/api/auth/me", "/api/sources", "/api/workspaces"):
        assert tenant.get(path).status_code == 401


@req("AUTH4")
def test_auth4_nothing_business_related_answers_without_signing_in(client):
    """Every tenant route refuses an anonymous request."""
    from fastapi.routing import APIRoute

    from app.main import app

    public = {"/api/health", "/api/research/latest", "/api/auth/login", "/api/auth/logout"}
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.startswith("/api") and route.path not in public:
            method = sorted(route.methods - {"HEAD", "OPTIONS"})[0]
            path = route.path.replace("{source_id}", "x").replace("{insight_id}", "x").replace("{workspace_id}", "x")
            assert client.request(method, path).status_code == 401, route.path


@req("CHAT1")
def test_chat1_a_conversation_reloads_intact(indexed):
    """Questions, answers, confidence and citations come back exactly as they were shown."""
    shown = [indexed.ask(q, session_id="sess_accept") for q in ("edit an invoice after sending", "and refunds?")]
    reloaded = indexed.get("/api/chat/history?session_id=sess_accept").json()
    assert [m["text"] for m in reloaded if m["role"] == "customer"] == ["edit an invoice after sending", "and refunds?"]
    assert [m for m in reloaded if m["role"] == "assistant"] == shown


@req("AUTH1", "AUTH2", "AUTH3", "CHAT1", "MT1")
def test_uj8_sign_in_ask_leave_come_back_sign_out(tenant, site):
    """UJ8. The browser session, end to end.

    Given a user with an account
    When they sign in, index their docs, ask two questions, leave the Ask page and
         come back (a fresh history load), then sign out
    Then the conversation is still there with its citations, and after signing out
         the token no longer works and the history is not readable.
    """
    token = tenant.sign_in()
    tenant.token = token
    tenant.add_website(f"{site}/docs/")
    tenant.ask("how long does a team invite last", session_id="sess_uj8")
    tenant.ask("and how do i change a member role", session_id="sess_uj8")

    back = tenant.get("/api/chat/history?session_id=sess_uj8").json()
    assert len(back) == 4 and back[1]["citations"] and back[3]["citations"]

    tenant.post("/api/auth/logout")
    assert tenant.get("/api/chat/history?session_id=sess_uj8").status_code == 401
    tenant.token = tenant.sign_in()  # signing back in restores access to the same history
    assert len(tenant.get("/api/chat/history?session_id=sess_uj8").json()) == 4
