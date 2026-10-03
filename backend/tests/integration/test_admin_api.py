"""Admin endpoints: authorization, validation and regression tests for known bugs."""
from __future__ import annotations

import pytest

from app.extensions import db
from app.models import ExternalUserMapping, Organization, User, UserEntityOwnership
from app.security import MASK

from ..conftest import TEST_PASSWORD

ADMIN_GET_ROUTES = ["/admin/dashboard"]


@pytest.mark.parametrize("path", ADMIN_GET_ROUTES)
def test_admin_routes_reject_anonymous_and_members(client, path, member_headers):
    assert client.get(path).status_code == 401
    assert client.get(path, headers=member_headers).status_code == 403


def test_every_admin_route_rejects_members(client, app, member, member_headers, org):
    """Walk the URL map so a newly added /admin route cannot ship without an authorization check."""
    uid = str(member.id)
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith("/admin"):
            continue
        path = (
            rule.rule.replace("<user_id>", uid)
            .replace("<org_id>", str(org.id))
            .replace("<entity_type>", "contact")
            .replace("<external_entity_id>", "1")
            .replace("<crm_type>", "hubspot")
        )
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            response = client.open(path, method=method, headers=member_headers, json={})
            assert response.status_code == 403, f"{method} {rule.rule} is reachable by a non-admin"
            assert client.open(path, method=method, json={}).status_code == 401


def test_dashboard_for_admin(client, admin, member, admin_headers):
    body = client.get("/admin/dashboard", headers=admin_headers).get_json()
    assert body["stats"] == {"total_organizations": 1, "total_users": 2}
    assert "password" not in str(body).lower()


# ---------------------------------------------------------------- organizations


def test_create_org_validation(client, admin_headers):
    assert client.post("/admin/organizations", headers=admin_headers, json={}).status_code == 400
    assert client.post("/admin/organizations", headers=admin_headers, json={"name": "  "}).status_code == 400
    bad = {"name": "X", "connector_type": "oracle"}
    assert client.post("/admin/organizations", headers=admin_headers, json=bad).status_code == 400


def test_create_org_defaults_and_trims(client, admin_headers):
    response = client.post("/admin/organizations", headers=admin_headers, json={"name": "  New Co "})
    assert response.status_code == 201
    assert response.get_json()["organization"]["connector_type"] == "internal"
    assert Organization.query.filter_by(name="New Co").count() == 1


def test_update_org_masks_config_in_response_and_keeps_stored_secret(client, org, admin_headers):
    cfg = {"api_key": "hs-secret-key"}
    r = client.put(f"/admin/organizations/{org.id}", headers=admin_headers, json={"connector_type": "hubspot", "connector_config": cfg})
    assert r.status_code == 200 and "hs-secret-key" not in r.get_data(as_text=True)
    assert r.get_json()["organization"]["connector_config"]["api_key"] == MASK

    r = client.put(
        f"/admin/organizations/{org.id}",
        headers=admin_headers,
        json={"name": "Renamed", "connector_config": {"api_key": MASK, "verify_ssl": True}},
    )
    assert r.status_code == 200
    db.session.expire_all()
    stored = db.session.get(Organization, org.id)
    assert stored.name == "Renamed" and stored.connector_config["api_key"] == "hs-secret-key"


def test_update_org_validates_connector(client, org, admin_headers):
    r = client.put(f"/admin/organizations/{org.id}", headers=admin_headers, json={"connector_type": "nope"})
    assert r.status_code == 400
    assert client.put("/admin/organizations/00000000-0000-0000-0000-000000000000", headers=admin_headers, json={}).status_code == 404


def test_delete_org_and_missing(client, make_org, admin_headers):
    other = make_org(name="Doomed")
    assert client.delete(f"/admin/organizations/{other.id}", headers=admin_headers).status_code == 200
    assert client.delete(f"/admin/organizations/{other.id}", headers=admin_headers).status_code == 404


# ---------------------------------------------------------------- users


def create_user_payload(org, **overrides):
    payload = {"email": "New.User@Acme.test", "password": "Passw0rd-ok", "org_id": str(org.id)}
    payload.update(overrides)
    return payload


def test_create_user_normalizes_email_and_can_log_in(client, org, admin_headers):
    r = client.post("/admin/users", headers=admin_headers, json=create_user_payload(org))
    assert r.status_code == 201
    assert r.get_json()["user"]["email"] == "new.user@acme.test"
    assert client.post("/login", json={"email": "NEW.user@acme.test", "password": "Passw0rd-ok"}).status_code == 200


@pytest.mark.parametrize(
    "overrides,status",
    [
        ({"email": "not-an-email"}, 400),
        ({"password": "short"}, 400),
        ({"role": "superuser"}, 400),
        ({"org_id": None}, 400),
        ({"org_id": "00000000-0000-0000-0000-000000000000"}, 404),
    ],
)
def test_create_user_validation(client, org, admin_headers, overrides, status):
    r = client.post("/admin/users", headers=admin_headers, json=create_user_payload(org, **overrides))
    assert r.status_code == status


def test_create_user_missing_fields_and_duplicates(client, org, admin, admin_headers):
    assert client.post("/admin/users", headers=admin_headers, json={"email": "a@b.co"}).status_code == 400
    dup = create_user_payload(org, email=admin.email.upper())
    assert client.post("/admin/users", headers=admin_headers, json=dup).status_code == 409


def test_update_user(client, org, make_org, make_user, admin, admin_headers):
    target = make_user(org, email="t@acme.test")
    other_org = make_org(name="Other")
    r = client.put(
        f"/admin/users/{target.id}",
        headers=admin_headers,
        json={"email": "T2@Acme.test", "role": "owner", "org_id": str(other_org.id)},
    )
    assert r.status_code == 200
    body = r.get_json()["user"]
    assert body == {"id": str(target.id), "email": "t2@acme.test", "org_id": str(other_org.id), "role": "owner"}


def test_update_user_validation(client, org, make_user, admin, admin_headers):
    target = make_user(org, email="t@acme.test")
    url = f"/admin/users/{target.id}"
    assert client.put(url, headers=admin_headers, json={"email": "bad"}).status_code == 400
    assert client.put(url, headers=admin_headers, json={"email": admin.email}).status_code == 409
    assert client.put(url, headers=admin_headers, json={"role": "god"}).status_code == 400
    assert client.put(url, headers=admin_headers, json={"org_id": "00000000-0000-0000-0000-000000000000"}).status_code == 404
    assert client.put("/admin/users/00000000-0000-0000-0000-000000000000", headers=admin_headers, json={}).status_code == 404


def test_admin_cannot_remove_own_admin_role_or_delete_self(client, admin, admin_headers):
    assert client.put(f"/admin/users/{admin.id}", headers=admin_headers, json={"role": "user"}).status_code == 400
    assert client.delete(f"/admin/users/{admin.id}", headers=admin_headers).status_code == 400
    assert db.session.get(User, admin.id).role == "admin"


def test_user_can_be_detached_from_org(client, org, make_user, admin_headers):
    target = make_user(org, email="t@acme.test")
    r = client.put(f"/admin/users/{target.id}", headers=admin_headers, json={"org_id": None})
    assert r.status_code == 200 and r.get_json()["user"]["org_id"] is None


def test_delete_user_cascades(client, org, make_user, admin_headers):
    target = make_user(org, email="t@acme.test")
    db.session.add(UserEntityOwnership(user_id=target.id, org_id=org.id, entity_type="contact", external_entity_id="1"))
    db.session.commit()
    assert client.delete(f"/admin/users/{target.id}", headers=admin_headers).status_code == 200
    assert client.delete(f"/admin/users/{target.id}", headers=admin_headers).status_code == 404


def test_reset_password_regression_user_can_log_in_afterwards(client, member, admin_headers):
    """Regression: reset used werkzeug hashes while login verifies bcrypt, locking the user out."""
    r = client.put(f"/admin/users/{member.id}/reset-password", headers=admin_headers, json={"password": "Br4nd-new-pass"})
    assert r.status_code == 200
    assert client.post("/login", json={"email": member.email, "password": "Br4nd-new-pass"}).status_code == 200
    assert client.post("/login", json={"email": member.email, "password": TEST_PASSWORD}).status_code == 401


def test_reset_password_validation(client, member, admin_headers):
    url = f"/admin/users/{member.id}/reset-password"
    assert client.put(url, headers=admin_headers, json={}).status_code == 400
    assert client.put(url, headers=admin_headers, json={"password": "short"}).status_code == 400
    assert client.put("/admin/users/00000000-0000-0000-0000-000000000000/reset-password", headers=admin_headers, json={"password": "long-enough"}).status_code == 404


def test_malformed_user_id_is_400_not_500(client, admin_headers):
    assert client.put("/admin/users/not-a-uuid", headers=admin_headers, json={}).status_code == 400


# ---------------------------------------------------------------- entity ownership


def test_entity_ownership_lifecycle(client, member, admin_headers):
    base = f"/admin/users/{member.id}/entity-ownership"
    r = client.post(base, headers=admin_headers, json={"entity_type": "contact", "external_entity_id": 77})
    assert r.status_code == 201
    listing = client.get(base, headers=admin_headers).get_json()
    assert listing["total_entities"] == 1 and listing["entities"][0]["external_entity_id"] == "77"
    assert client.get(base + "?entity_type=deal", headers=admin_headers).get_json()["total_entities"] == 0
    assert client.delete(f"{base}/contact/77", headers=admin_headers).status_code == 200
    assert client.delete(f"{base}/contact/77", headers=admin_headers).status_code == 404


def test_entity_ownership_validation(client, member, admin_headers):
    base = f"/admin/users/{member.id}/entity-ownership"
    assert client.post(base, headers=admin_headers, json={"entity_type": "contact"}).status_code == 400
    assert client.post("/admin/users/00000000-0000-0000-0000-000000000000/entity-ownership", headers=admin_headers, json={}).status_code == 404
    assert client.get("/admin/users/00000000-0000-0000-0000-000000000000/entity-ownership", headers=admin_headers).status_code == 404


def test_bulk_entity_assignment_partial_failures(client, member, admin_headers):
    payload = {
        "assignments": [
            {"user_id": str(member.id), "entity_type": "contact", "external_entity_id": "1"},
            {"user_id": str(member.id), "entity_type": "contact"},
            {"user_id": "00000000-0000-0000-0000-000000000000", "entity_type": "contact", "external_entity_id": "2"},
        ]
    }
    r = client.post("/admin/entity-ownership/bulk", headers=admin_headers, json=payload)
    assert r.status_code == 207
    body = r.get_json()
    assert (body["successful"], body["failed"]) == (1, 2) and len(body["errors"]) == 2
    assert client.post("/admin/entity-ownership/bulk", headers=admin_headers, json={"assignments": []}).status_code == 400


# ---------------------------------------------------------------- external user mapping


def test_external_mapping_lifecycle(client, org, member, admin_headers):
    payload = {
        "user_id": str(member.id), "org_id": str(org.id), "crm_type": "HubSpot",
        "external_user_id": "555", "external_email": "m@hs.test",
    }
    assert client.post("/admin/external-user-mapping", headers=admin_headers, json=payload).status_code == 201
    assert client.get(f"/admin/external-user-mapping/{member.id}", headers=admin_headers).get_json()["crm_mappings"] == {"hubspot": "555"}
    listing = client.get(f"/admin/crm-users/{org.id}/hubspot", headers=admin_headers).get_json()
    assert listing["total_mappings"] == 1 and listing["mappings"][0]["user_email"] == member.email
    assert client.delete(f"/admin/external-user-mapping/{member.id}/hubspot", headers=admin_headers).status_code == 200
    assert client.delete(f"/admin/external-user-mapping/{member.id}/hubspot", headers=admin_headers).status_code == 404
    assert ExternalUserMapping.query.count() == 0


def test_external_mapping_rejects_user_from_other_org(client, make_org, member, admin_headers):
    other = make_org(name="Other")
    payload = {"user_id": str(member.id), "org_id": str(other.id), "crm_type": "hubspot", "external_user_id": "1"}
    assert client.post("/admin/external-user-mapping", headers=admin_headers, json=payload).status_code == 404
    assert client.post("/admin/external-user-mapping", headers=admin_headers, json={"user_id": "x"}).status_code == 400


def test_external_mapping_unknown_ids(client, admin_headers):
    zero = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/admin/external-user-mapping/{zero}", headers=admin_headers).status_code == 404
    assert client.get(f"/admin/crm-users/{zero}/hubspot", headers=admin_headers).status_code == 404
    assert client.delete(f"/admin/external-user-mapping/{zero}/hubspot", headers=admin_headers).status_code == 404


def test_bulk_external_mapping(client, org, member, admin_headers):
    payload = {
        "org_id": str(org.id),
        "crm_type": "salesforce",
        "mappings": [
            {"lia_user_email": member.email.upper(), "external_user_id": "SF-1"},
            {"lia_user_email": "ghost@acme.test", "external_user_id": "SF-2"},
            {"lia_user_email": member.email},
        ],
    }
    r = client.post("/admin/external-user-mapping/bulk", headers=admin_headers, json=payload)
    assert r.status_code == 207
    assert (r.get_json()["successful"], r.get_json()["failed"]) == (1, 2)
    assert client.post("/admin/external-user-mapping/bulk", headers=admin_headers, json={"org_id": str(org.id)}).status_code == 400
    bad_org = {**payload, "org_id": "00000000-0000-0000-0000-000000000000"}
    assert client.post("/admin/external-user-mapping/bulk", headers=admin_headers, json=bad_org).status_code == 404
