"""The sign-in and organisation boundary, checked over every route the app exposes."""

from __future__ import annotations

import re

import pytest
from fastapi.routing import APIRoute

from app.main import app

PUBLIC = {"/api/health", "/api/research/latest", "/api/auth/login", "/api/auth/logout"}
SESSION_ONLY = {"/api/auth/me"}  # needs a session, but no organisation or workspace


def _routes():
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.startswith("/api"):
            for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
                yield method, route.path


PROTECTED = [(m, p) for m, p in _routes() if p not in PUBLIC]
TENANT_ROUTES = [(m, p) for m, p in PROTECTED if p not in SESSION_ONLY]


def _fill(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "x_unknown", path)


def _body(method):
    return {} if method in ("POST", "PATCH") else None


def test_route_inventory_is_complete():
    """Guard: the lists grow automatically with the app, so new routes are covered."""
    assert len(TENANT_ROUTES) >= 19


@pytest.mark.parametrize("method,path", PROTECTED)
def test_every_protected_route_requires_a_session(client, method, path):
    """No route outside the public ones answers without signing in."""
    resp = client.request(method, _fill(path), json=_body(method))
    assert resp.status_code == 401, f"{method} {path} returned {resp.status_code}"
    assert resp.headers.get("www-authenticate") == "Bearer"


@pytest.mark.parametrize("method,path", TENANT_ROUTES)
def test_the_organisation_header_alone_is_not_trusted(client, method, path):
    """A browser naming an organisation without signing in gets nothing."""
    resp = client.request(method, _fill(path), json=_body(method), headers={"X-Organization-Id": "org_default"})
    assert resp.status_code == 401


@pytest.mark.parametrize("method,path", TENANT_ROUTES)
def test_internal_callers_must_name_the_organisation(client, method, path):
    """With the internal key, X-Organization-Id is required and validated."""
    from conftest import INTERNAL_KEY

    resp = client.request(method, _fill(path), json=_body(method), headers={"X-Internal-Key": INTERNAL_KEY})
    assert resp.status_code == 400 and "X-Organization-Id" in resp.json()["detail"]


def test_a_wrong_internal_key_is_refused(client):
    resp = client.get("/api/sources", headers={"X-Internal-Key": "guess", "X-Organization-Id": "org_default"})
    assert resp.status_code == 401


@pytest.mark.parametrize("path", ["/api/health", "/api/research/latest"])
def test_public_routes_need_no_sign_in(client, path):
    assert client.get(path).status_code in (200, 404)


def test_a_signed_in_user_cannot_name_another_organisation(tenant):
    """The session decides the organisation; asking for a different one is 403."""
    resp = tenant.client.get("/api/sources", headers={**tenant.headers(), "X-Organization-Id": "org_someone_else"})
    assert resp.status_code == 403
    same = tenant.client.get("/api/sources", headers={**tenant.headers(), "X-Organization-Id": tenant.org})
    assert same.status_code == 200


def test_internal_path_sees_the_same_data_as_the_session(indexed):
    """A trusted server naming the organisation sees exactly what its users see."""
    via_session = indexed.get("/api/sources").json()
    via_internal = indexed.client.get("/api/sources", headers=indexed.internal_headers()).json()
    assert via_session == via_internal


def test_another_organisation_sees_none_of_it(with_traffic, make_tenant):
    """Every read endpoint, asked by another organisation, shows none of the first one's data."""
    other = make_tenant()
    assert other.get("/api/sources").json() == []
    assert other.get("/api/insights").json() == []
    assert other.get("/api/periods").json() == []
    assert other.get("/api/reports").json() == []
    assert other.get("/api/reports/latest").status_code == 404
    assert other.get("/api/evaluation/latest").status_code == 404
    assert other.get("/api/overview").json()["queryCount"] == 0
    names = [w["name"] for w in other.get("/api/workspaces").json()]
    assert names == ["Default workspace"]
    assert other.ask("edit an invoice after sending")["citations"] == []


def test_another_organisation_cannot_touch_its_ids(with_traffic, make_tenant):
    """Ids from one organisation are 404 for another, for reads and writes."""
    other = make_tenant()
    source_id = with_traffic.site_source["id"]
    insight_id = with_traffic.get("/api/insights").json()[0]["id"]
    ws = with_traffic.default_workspace
    assert other.get(f"/api/insights/{insight_id}").status_code == 404
    assert other.post(f"/api/sources/{source_id}/reindex").status_code == 404
    assert other.post(f"/api/sources/{source_id}/stop").status_code == 404
    assert other.delete(f"/api/sources/{source_id}").status_code == 404
    assert other.patch(f"/api/workspaces/{ws}", json={"name": "taken"}).status_code == 404
    assert other.delete(f"/api/workspaces/{ws}").status_code == 404
    assert other.get("/api/sources", workspace=ws).status_code == 404
    assert other.get("/api/chat/history?session_id=sess_test", workspace=ws).status_code == 404
    assert with_traffic.source(source_id)["status"] == "ready"
    assert with_traffic.get(f"/api/insights/{insight_id}").status_code == 200


def test_same_site_indexed_by_two_organisations_stays_separate(indexed, make_tenant, site):
    """Two tenants indexing the same URL get independent sources and chunks."""
    other = make_tenant()
    theirs = other.add_website(f"{site}/docs/")
    assert theirs["id"] != indexed.site_source["id"]
    mine = {c["chunkId"] for c in indexed.ask("invite a team member")["citations"]}
    their = {c["chunkId"] for c in other.ask("invite a team member")["citations"]}
    assert mine and their and not (mine & their)
