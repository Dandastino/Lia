"""Authentication, rate limiting and GDPR self-service endpoints."""
from __future__ import annotations

import pytest

from app import create_app
from app.extensions import db, limiter
from app.models import ExternalUserMapping, User, UserEntityOwnership

from ..conftest import TEST_PASSWORD, build_test_config


def test_login_success_returns_token_and_user(client, member, org):
    response = client.post("/login", json={"email": "Member@Acme.test ", "password": TEST_PASSWORD})
    body = response.get_json()
    assert response.status_code == 200
    assert body["access_token"]
    assert body["user"] == {
        "id": str(member.id),
        "email": "member@acme.test",
        "org_id": str(org.id),
        "org_name": "Acme",
        "role": "user",
    }


@pytest.mark.parametrize(
    "payload",
    [{}, {"email": "a@b.co"}, {"password": "x"}, {"email": "", "password": ""}, {"email": "a@b.co", "password": 123}],
)
def test_login_missing_fields_is_400(client, payload):
    assert client.post("/login", json=payload).status_code == 400


def test_login_non_object_body_is_400(client):
    assert client.post("/login", json=["x"]).status_code == 400


def test_login_unknown_email_and_wrong_password_are_indistinguishable(client, member):
    unknown = client.post("/login", json={"email": "nobody@acme.test", "password": "whatever1"})
    wrong = client.post("/login", json={"email": member.email, "password": "wrong-password"})
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.get_json() == wrong.get_json() == {"error": "Invalid email or password"}


def test_login_user_without_org_is_rejected(client, make_user):
    make_user(None, email="orphan@acme.test")
    response = client.post("/login", json={"email": "orphan@acme.test", "password": TEST_PASSWORD})
    assert response.status_code == 403


def test_protected_route_requires_token(client):
    assert client.get("/organizations").status_code == 401
    assert client.get("/meetings").status_code == 401
    assert client.get("/getToken").status_code == 401


def test_garbage_token_is_rejected(client):
    response = client.get("/organizations", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 422


def test_login_is_rate_limited(app):
    limited_app = create_app(build_test_config(RATELIMIT_ENABLED=True, LOGIN_RATE_LIMIT="3 per minute"))
    try:
        client = limited_app.test_client()
        statuses = [
            client.post("/login", json={"email": "x@y.zz", "password": "bad-password"}).status_code for _ in range(5)
        ]
        assert statuses[:3] == [401, 401, 401]
        assert statuses[3:] == [429, 429]
    finally:
        # The Limiter is a module-level singleton shared by every app instance.
        limiter.reset()
        limiter.enabled = False


def test_security_headers_present(client):
    response = client.get("/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Cache-Control"] == "no-store"


def test_cors_allows_only_configured_origin(client):
    ok = client.get("/health", headers={"Origin": "http://localhost:3000"})
    bad = client.get("/health", headers={"Origin": "https://evil.example"})
    assert ok.headers.get("Access-Control-Allow-Origin") == "http://localhost:3000"
    assert "Access-Control-Allow-Origin" not in bad.headers
    assert "Access-Control-Allow-Credentials" not in ok.headers


def test_unknown_route_returns_json_404(client):
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    assert response.get_json() == {"error": "Not Found"}


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json()["status"] == "healthy"


def test_root_lists_endpoints(client):
    assert client.get("/").get_json()["name"] == "Lia Assistant API"


# ---------------------------------------------------------------- GDPR / self-service


def test_export_my_data(client, member, member_headers):
    db.session.add(UserEntityOwnership(user_id=member.id, org_id=member.org_id, entity_type="contact", external_entity_id="7"))
    db.session.add(
        ExternalUserMapping(
            user_id=member.id, org_id=member.org_id, crm_type="hubspot", external_user_id="99", external_email="m@hs.test"
        )
    )
    db.session.commit()

    body = client.get("/me/export", headers=member_headers).get_json()
    assert body["user"]["email"] == member.email
    assert "password_hash" not in str(body)
    assert body["entity_ownership"][0]["external_entity_id"] == "7"
    assert body["external_user_mappings"][0]["crm_type"] == "hubspot"


def test_delete_my_account_requires_correct_password(client, member, member_headers):
    wrong = client.delete("/me", headers=member_headers, json={"password": "nope-nope"})
    assert wrong.status_code == 403
    assert db.session.get(User, member.id) is not None

    ok = client.delete("/me", headers=member_headers, json={"password": TEST_PASSWORD})
    assert ok.status_code == 200
    db.session.expire_all()
    assert db.session.get(User, member.id) is None


def test_change_password_flow(client, member, member_headers):
    bad_current = client.put("/me/password", headers=member_headers, json={"current_password": "x", "new_password": "NewPassw0rd!"})
    assert bad_current.status_code == 403
    weak = client.put("/me/password", headers=member_headers, json={"current_password": TEST_PASSWORD, "new_password": "short"})
    assert weak.status_code == 400
    ok = client.put("/me/password", headers=member_headers, json={"current_password": TEST_PASSWORD, "new_password": "NewPassw0rd!"})
    assert ok.status_code == 200
    assert client.post("/login", json={"email": member.email, "password": "NewPassw0rd!"}).status_code == 200
    assert client.post("/login", json={"email": member.email, "password": TEST_PASSWORD}).status_code == 401
